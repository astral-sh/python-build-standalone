# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "packaging>=24",
# ]
# ///

"""Find and optionally apply updates to pythonbuild/downloads.py.

From the repository root, run ``uv run scripts/update_downloads.py`` to list
possible updates. Pass one or more package names and ``--write`` to download
those artifacts, calculate their metadata, and update the download table.

Version discovery is intentionally configured per package. Many dependencies
have a release-series constraint or an artifact URL that cannot be inferred
safely from the URL currently recorded in the download table.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import dataclasses
import hashlib
import html.parser
import json
import os
import pathlib
import re
import shlex
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Protocol, cast

from packaging.version import InvalidVersion, Version

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOWNLOADS_PATH = ROOT / "pythonbuild" / "downloads.py"
DISTTESTS_PATH = ROOT / "pythonbuild" / "disttests" / "__init__.py"
DEFAULT_STAGING_DIR = ROOT / "build" / "download-updates"
MIRROR_BASE_URL = "https://astral-sh.github.io/mirror/files/"
USER_AGENT = "python-build-standalone update-downloads"


@dataclasses.dataclass(frozen=True)
class Release:
    version: str
    url: str


class Discovery(Protocol):
    def releases(self, client: HttpClient) -> Iterable[Release]: ...


@dataclasses.dataclass(frozen=True)
class Policy:
    discovery: Discovery
    series_components: int = 0
    allow_prereleases: bool = False
    mirrored: bool = False
    note: str | None = None
    version_parser: Callable[[str], Version] = Version

    def accepts(self, candidate: Version, current: Version) -> bool:
        if candidate <= current:
            return False
        if candidate.is_prerelease and not self.allow_prereleases:
            return False
        if self.series_components:
            count = self.series_components
            return candidate.release[:count] == current.release[:count]
        return True


@dataclasses.dataclass(frozen=True)
class CheckResult:
    package: str
    current_version: str
    release: Release | None = None
    error: str | None = None


class HttpClient:
    def __init__(self, github_token: str | None = None) -> None:
        self.github_token = github_token

    def open(self, url: str) -> Any:
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        if self.github_token and urllib.parse.urlparse(url).netloc == "api.github.com":
            headers["Authorization"] = f"Bearer {self.github_token}"
        request = urllib.request.Request(url, headers=headers)
        return urllib.request.urlopen(request, timeout=60)

    def text(self, url: str) -> str:
        with self.open(url) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return cast(str, response.read().decode(charset, errors="replace"))

    def json(self, url: str) -> Any:
        return json.loads(self.text(url))


class _LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


@dataclasses.dataclass(frozen=True)
class HtmlDiscovery:
    """Discover versions from links in a directory or release page."""

    index_url: str
    link_pattern: str
    artifact_url: str | None = None
    version_transform: Callable[[str], str] = lambda value: value

    def releases(self, client: HttpClient) -> Iterable[Release]:
        parser = _LinkParser()
        parser.feed(client.text(self.index_url))
        pattern = re.compile(self.link_pattern)
        for href in parser.links:
            match = pattern.search(urllib.parse.unquote(href))
            if not match:
                continue
            version = self.version_transform(match.group("version"))
            url = (
                self.artifact_url.format(version=version)
                if self.artifact_url
                else urllib.parse.urljoin(self.index_url, href)
            )
            yield Release(version, url)


@dataclasses.dataclass(frozen=True)
class GitHubReleaseDiscovery:
    """Discover release artifacts using the GitHub releases API."""

    repository: str
    tag_pattern: str
    artifact_name: str | None = None
    artifact_url: str | None = None
    version_transform: Callable[[str], str] = lambda value: value

    def releases(self, client: HttpClient) -> Iterable[Release]:
        url = f"https://api.github.com/repos/{self.repository}/releases?per_page=100"
        pattern = re.compile(self.tag_pattern)
        for item in client.json(url):
            if item.get("draft"):
                continue
            match = pattern.fullmatch(item["tag_name"])
            if not match:
                continue
            version = self.version_transform(match.group("version"))
            if self.artifact_name:
                expected = self.artifact_name.format(version=version)
                asset_url = next(
                    (
                        asset["browser_download_url"]
                        for asset in item.get("assets", [])
                        if asset["name"] == expected
                    ),
                    None,
                )
                if not asset_url:
                    continue
            elif self.artifact_url:
                asset_url = self.artifact_url.format(
                    version=version, tag=item["tag_name"]
                )
            else:
                raise ValueError("GitHub discovery needs an artifact name or URL")
            yield Release(version, asset_url)


@dataclasses.dataclass(frozen=True)
class PyPIDiscovery:
    project: str
    filename_pattern: str

    def releases(self, client: HttpClient) -> Iterable[Release]:
        data = client.json(f"https://pypi.org/pypi/{self.project}/json")
        pattern = re.compile(self.filename_pattern)
        for version, files in data["releases"].items():
            for file_data in files:
                if pattern.fullmatch(file_data["filename"]):
                    yield Release(version, file_data["url"])
                    break


def html_policy(
    index_url: str,
    link_pattern: str,
    *,
    artifact_url: str | None = None,
    series: int = 0,
    mirrored: bool = False,
    allow_prereleases: bool = False,
    version_transform: Callable[[str], str] = lambda value: value,
    version_parser: Callable[[str], Version] = Version,
) -> Policy:
    return Policy(
        HtmlDiscovery(index_url, link_pattern, artifact_url, version_transform),
        series_components=series,
        allow_prereleases=allow_prereleases,
        mirrored=mirrored,
        version_parser=version_parser,
    )


def github_policy(
    repository: str,
    tag_pattern: str,
    *,
    artifact_name: str | None = None,
    artifact_url: str | None = None,
    series: int = 0,
    mirrored: bool = False,
    version_transform: Callable[[str], str] = lambda value: value,
) -> Policy:
    return Policy(
        GitHubReleaseDiscovery(
            repository,
            tag_pattern,
            artifact_name,
            artifact_url,
            version_transform,
        ),
        series_components=series,
        mirrored=mirrored,
    )


def gnu_policy(name: str, extension: str, *, series: int = 0) -> Policy:
    return html_policy(
        f"https://ftp.gnu.org/gnu/{name}/",
        rf"(?:^|/){re.escape(name)}-(?P<version>[0-9]+(?:\.[0-9]+)*)"
        rf"\.{re.escape(extension)}$",
        series=series,
        mirrored=True,
    )


def cpython_policy(series: str, allow_prereleases: bool = False) -> Policy:
    escaped = re.escape(series)
    if allow_prereleases:
        return html_policy(
            f"https://www.python.org/ftp/python/{series}.0/",
            rf"^Python-(?P<version>{escaped}\.0"
            rf"(?:a[0-9]+|b[0-9]+|rc[0-9]+)?)\.tar\.xz$",
            series=2,
            allow_prereleases=True,
        )
    return html_policy(
        "https://www.python.org/ftp/python/",
        rf"^(?P<version>{escaped}\.[0-9]+)/$",
        artifact_url="https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz",
        series=2,
    )


def xorg_policy(category: str, name: str, extension: str = "tar.gz") -> Policy:
    return html_policy(
        f"https://www.x.org/releases/individual/{category}/",
        rf"(?:^|/){re.escape(name)}-(?P<version>[0-9][0-9A-Za-z.+-]*)"
        rf"\.{re.escape(extension)}$",
    )


POLICIES: dict[str, Policy] = {
    "autoconf": gnu_policy("autoconf", "tar.gz"),
    "binutils": gnu_policy("binutils", "tar.xz"),
    "bzip2": html_policy(
        "https://sourceware.org/pub/bzip2/",
        r"(?:^|/)bzip2-(?P<version>[0-9][0-9A-Za-z.+-]*)\.tar\.gz$",
        mirrored=True,
    ),
    "cpython-3.10": cpython_policy("3.10"),
    "cpython-3.11": cpython_policy("3.11"),
    "cpython-3.12": cpython_policy("3.12"),
    "cpython-3.13": cpython_policy("3.13"),
    "cpython-3.14": cpython_policy("3.14"),
    "cpython-3.15": cpython_policy("3.15", allow_prereleases=True),
    "expat": github_policy(
        "libexpat/libexpat",
        r"R_(?P<version>[0-9_]+)",
        artifact_name="expat-{version}.tar.xz",
        version_transform=lambda value: value.replace("_", "."),
    ),
    "libedit": html_policy(
        "https://thrysoee.dk/editline/",
        r"(?:^|/)libedit-(?P<version>[0-9][0-9A-Za-z.+-]*)\.tar\.gz$",
        version_parser=lambda value: Version(value.replace("-", ".")),
    ),
    "libffi": github_policy(
        "libffi/libffi",
        r"v(?P<version>[0-9.]+)",
        artifact_name="libffi-{version}.tar.gz",
        series=2,
    ),
    "libpthread-stubs": xorg_policy("lib", "libpthread-stubs"),
    "libX11": xorg_policy("lib", "libX11"),
    "libXau": xorg_policy("lib", "libXau"),
    "libxcb": html_policy(
        "https://xcb.freedesktop.org/dist/",
        r"(?:^|/)libxcb-(?P<version>[0-9][0-9A-Za-z.+-]*)\.tar\.gz$",
    ),
    "m4": gnu_policy("m4", "tar.xz"),
    "mpdecimal": html_policy(
        "https://www.bytereef.org/mpdecimal/changelog.html",
        r"^#version-(?P<version>[0-9-]+)$",
        artifact_url=(
            "https://www.bytereef.org/software/mpdecimal/releases/"
            "mpdecimal-{version}.tar.gz"
        ),
        mirrored=True,
        version_transform=lambda value: value.replace("-", "."),
    ),
    "ncurses": gnu_policy("ncurses", "tar.gz"),
    "openssl-3.5": github_policy(
        "openssl/openssl",
        r"openssl-(?P<version>3\.5\.[0-9]+)",
        artifact_name="openssl-{version}.tar.gz",
        series=2,
    ),
    "nasm-windows-bin": html_policy(
        "https://www.nasm.us/pub/nasm/releasebuilds/",
        r"^(?P<version>[0-9][0-9.]*)/$",
        artifact_url=(
            "https://www.nasm.us/pub/nasm/releasebuilds/{version}/win64/"
            "nasm-{version}-win64.zip"
        ),
        mirrored=True,
    ),
    "patchelf": github_policy(
        "NixOS/patchelf",
        r"(?P<version>[0-9.]+)",
        artifact_name="patchelf-{version}.tar.bz2",
    ),
    "pip": Policy(PyPIDiscovery("pip", r"pip-[0-9A-Za-z.+-]+-py3-none-any\.whl")),
    "setuptools": Policy(
        PyPIDiscovery("setuptools", r"setuptools-[0-9A-Za-z.+-]+-py3-none-any\.whl")
    ),
    "tcl": html_policy(
        "https://www.tcl-lang.org/software/tcltk/download.html",
        r"(?:^|/)tcl(?P<version>[0-9]+(?:\.[0-9]+)+(?:a[0-9]+|b[0-9]+|rc[0-9]+)?)-src\.tar\.gz$",
        artifact_url="https://prdownloads.sourceforge.net/tcl/tcl{version}-src.tar.gz",
        series=2,
    ),
    "tk": html_policy(
        "https://www.tcl-lang.org/software/tcltk/download.html",
        r"(?:^|/)tk(?P<version>[0-9]+(?:\.[0-9]+)+(?:a[0-9]+|b[0-9]+|rc[0-9]+)?)-src\.tar\.gz$",
        artifact_url="https://prdownloads.sourceforge.net/tcl/tk{version}-src.tar.gz",
        series=2,
    ),
    "x11-util-macros": xorg_policy("util", "util-macros"),
    "xcb-proto": html_policy(
        "https://xcb.freedesktop.org/dist/",
        r"(?:^|/)xcb-proto-(?P<version>[0-9][0-9A-Za-z.+-]*)\.tar\.xz$",
    ),
    "xorgproto": xorg_policy("proto", "xorgproto"),
    "xtrans": xorg_policy("lib", "xtrans"),
    "xz": github_policy(
        "tukaani-project/xz",
        r"v(?P<version>[0-9.]+)",
        artifact_name="xz-{version}.tar.gz",
    ),
    "zlib": github_policy(
        "madler/zlib",
        r"v(?P<version>[0-9.]+)",
        artifact_name="zlib-{version}.tar.gz",
    ),
}


UNSUPPORTED: dict[str, str] = {
    "bdb": "pinned to the last Sleepycat-licensed release",
    "jom-windows-bin": "Qt's release layout needs a dedicated policy",
    "libffi-3.3": "intentionally pinned for compatibility",
    "llvm-aarch64-linux": "toolchain bootstrap requires coordinated updates",
    "llvm-x86_64-linux": "toolchain bootstrap requires coordinated updates",
    "llvm-aarch64-macos": "toolchain bootstrap requires coordinated updates",
    "llvm-x86_64-macos": "toolchain bootstrap requires coordinated updates",
    "musl": "intentionally pinned build toolchain",
    "musl-static": "intentionally pinned build toolchain",
    "openssl-1.1": "end-of-life release series",
    "sqlite": "requires SQLite's numeric-version and release-year mapping",
    "strawberryperl": "Windows toolchain update requires manual validation",
    "tix": "source dependency snapshot",
    "tcl-8612": "legacy compatibility version",
    "tk-8612": "legacy compatibility version",
    "tk-windows-bin-903": "commit-pinned CPython binary dependency",
    "tk-windows-bin-8614": "commit-pinned CPython binary dependency",
    "tk-windows-bin-8612": "commit-pinned CPython binary dependency",
    "uuid": "inactive upstream project",
    "zlib-ng": "CPython source-deps snapshot must follow the upstream release",
    "zstd": "CPython source-deps snapshot must follow the upstream release",
}


def load_downloads(path: pathlib.Path = DOWNLOADS_PATH) -> dict[str, dict[str, Any]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DOWNLOADS"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict):
                break
            return value
    raise ValueError(f"could not find a literal DOWNLOADS dictionary in {path}")


def find_update(
    package: str,
    entry: dict[str, Any],
    policy: Policy,
    client: HttpClient,
) -> CheckResult:
    current_text = entry["version"]
    if not isinstance(current_text, str):
        return CheckResult(package, str(current_text), error="version is not a string")
    try:
        current = policy.version_parser(current_text)
        candidates: list[tuple[Version, Release]] = []
        for release in policy.discovery.releases(client):
            try:
                candidates.append((policy.version_parser(release.version), release))
            except InvalidVersion:
                continue
        if not candidates:
            raise ValueError("no parseable releases discovered")
        accepted = [item for item in candidates if policy.accepts(item[0], current)]
        selected_release = (
            max(accepted, key=lambda item: item[0])[1] if accepted else None
        )
        return CheckResult(package, current_text, selected_release)
    except Exception as exc:
        return CheckResult(package, current_text, error=str(exc))


def find_updates(
    downloads: dict[str, dict[str, Any]],
    packages: Sequence[str],
    client: HttpClient,
    workers: int,
) -> list[CheckResult]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                find_update, package, downloads[package], POLICIES[package], client
            ): package
            for package in packages
        }
        results = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]
    return sorted(results, key=lambda result: result.package.lower())


def artifact_metadata(client: HttpClient, url: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with client.open(url) as response:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def artifact_filename(url: str) -> str:
    filename = pathlib.PurePosixPath(urllib.parse.urlparse(url).path).name
    if not filename:
        raise ValueError(f"could not determine artifact filename from {url}")
    return filename


def stage_artifact(
    client: HttpClient, url: str, staging_dir: pathlib.Path
) -> tuple[pathlib.Path, int, str]:
    staging_dir.mkdir(parents=True, exist_ok=True)
    path = staging_dir / artifact_filename(url)
    temporary_path = path.with_name(f".{path.name}.part")
    digest = hashlib.sha256()
    size = 0
    try:
        with client.open(url) as response, temporary_path.open("wb") as destination:
            while chunk := response.read(1024 * 1024):
                destination.write(chunk)
                size += len(chunk)
                digest.update(chunk)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return path, size, digest.hexdigest()


def stored_url(release: Release, policy: Policy, upstream_urls: bool) -> str:
    if not policy.mirrored or upstream_urls:
        return release.url
    return urllib.parse.urljoin(MIRROR_BASE_URL, artifact_filename(release.url))


def print_mirror_instructions(
    staged: dict[str, tuple[pathlib.Path, Release, str]],
) -> None:
    if not staged:
        return

    print("\nMirrored artifacts staged:", file=sys.stderr)
    for package, (path, release, sha256) in sorted(staged.items()):
        print(f"  {package}: {path}", file=sys.stderr)
        print(f"    upstream: {release.url}", file=sys.stderr)
        print(f"    sha256:   {sha256}", file=sys.stderr)

    print("\nBefore committing this update:", file=sys.stderr)
    print("1. Confirm each version and upstream URL are legitimate.", file=sys.stderr)
    print("2. Verify upstream signatures or checksums when available.", file=sys.stderr)
    print(
        "3. Copy each artifact into files/ in a checkout of "
        "https://github.com/astral-sh/mirror:",
        file=sys.stderr,
    )
    for path, release, _sha256 in sorted(staged.values()):
        filename = artifact_filename(release.url)
        print(
            f"   cp {shlex.quote(str(path))} "
            f"/path/to/mirror/files/{shlex.quote(filename)}",
            file=sys.stderr,
        )
    print("4. Commit and push the mirror change.", file=sys.stderr)
    print("5. Wait for GitHub Pages deployment, then verify:", file=sys.stderr)
    for _path, release, sha256 in sorted(staged.values()):
        mirror_url = urllib.parse.urljoin(
            MIRROR_BASE_URL, artifact_filename(release.url)
        )
        print(f"   {mirror_url}  sha256={sha256}", file=sys.stderr)


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


def update_download_literals(
    path: pathlib.Path,
    changes: dict[str, dict[str, Any]],
    source_comments: dict[str, tuple[str, bool]] | None = None,
) -> None:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    offsets = _line_offsets(source)
    replacements: list[tuple[int, int, str]] = []

    downloads_node: ast.Dict | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "DOWNLOADS"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Dict):
                downloads_node = node.value
            break
    if downloads_node is None:
        raise ValueError(f"could not locate DOWNLOADS in {path}")

    entries = {
        key.value: value
        for key, value in zip(downloads_node.keys, downloads_node.values, strict=True)
        if isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and isinstance(value, ast.Dict)
    }
    source_comments = source_comments or {}
    for package, fields in changes.items():
        entry = entries.get(package)
        if entry is None:
            raise KeyError(f"DOWNLOADS has no {package!r} entry")
        values = {
            key.value: value
            for key, value in zip(entry.keys, entry.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if package in source_comments:
            url_node = values.get("url")
            if url_node is None:
                raise KeyError(f"{package!r} has no editable 'url' field")
            lines = source.splitlines(keepends=True)
            for line_number in range(entry.lineno, url_node.lineno):
                line = lines[line_number - 1]
                match = re.match(
                    r"^(\s*)# (?:Mirrored from|Upstream source \(mirror pending\):) "
                    r"https?://",
                    line,
                )
                if not match:
                    continue
                upstream_url, using_mirror = source_comments[package]
                label = (
                    "Mirrored from"
                    if using_mirror
                    else "Upstream source (mirror pending):"
                )
                start = offsets[line_number - 1]
                end = offsets[line_number]
                replacements.append(
                    (
                        start,
                        end,
                        f"{match.group(1)}# {label} {upstream_url}\n",
                    )
                )
                break
            else:
                raise ValueError(f"{package!r} has no upstream source comment")
        for field, new_value in fields.items():
            field_node = values.get(field)
            if (
                field_node is None
                or field_node.end_lineno is None
                or field_node.end_col_offset is None
            ):
                raise KeyError(f"{package!r} has no editable {field!r} field")
            start = offsets[field_node.lineno - 1] + field_node.col_offset
            end = offsets[field_node.end_lineno - 1] + field_node.end_col_offset
            replacements.append((start, end, _literal(new_value)))

    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    path.write_text(source)


def update_openssl_disttest_version(
    version: str, path: pathlib.Path = DISTTESTS_PATH
) -> None:
    release = Version(version).release
    if len(release) != 3 or release[0] < 3:
        raise ValueError(f"cannot derive OpenSSL 3.x version info from {version!r}")
    wanted_version = (release[0], release[1], 0, release[2], 0)

    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    offsets = _line_offsets(source)
    matches: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == "wanted_version"
            for target in node.targets
        ):
            continue
        try:
            current_value = ast.literal_eval(node.value)
        except (SyntaxError, ValueError):
            continue
        if (
            isinstance(current_value, tuple)
            and len(current_value) == 5
            and current_value[0] == 3
        ):
            matches.append(node.value)

    if len(matches) != 1:
        raise ValueError(
            f"expected one OpenSSL 3.x wanted_version assignment in {path}; "
            f"found {len(matches)}"
        )
    node = matches[0]
    if node.end_lineno is None or node.end_col_offset is None:
        raise ValueError(f"could not locate OpenSSL version tuple in {path}")
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    path.write_text(source[:start] + _literal(wanted_version) + source[end:])


def validate_package_names(
    parser: argparse.ArgumentParser,
    requested: Sequence[str],
    downloads: dict[str, dict[str, Any]],
) -> list[str]:
    unknown = sorted(set(requested) - downloads.keys())
    if unknown:
        parser.error(f"unknown package(s): {', '.join(unknown)}")
    unsupported = sorted(set(requested) - POLICIES.keys())
    if unsupported:
        details = "; ".join(
            f"{name}: {UNSUPPORTED.get(name, 'no update policy')}"
            for name in unsupported
        )
        parser.error(f"cannot check package(s): {details}")
    return list(dict.fromkeys(requested))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages",
        nargs="*",
        metavar="PACKAGE",
        help="packages to check (default: every package with an update policy)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="download updates and modify pythonbuild/downloads.py",
    )
    parser.add_argument(
        "--upstream-urls",
        action="store_true",
        help="write upstream URLs instead of mirror URLs for mirrored packages",
    )
    parser.add_argument(
        "--staging-dir",
        type=pathlib.Path,
        default=DEFAULT_STAGING_DIR,
        help=(
            "directory for newly downloaded mirrored artifacts "
            f"(default: {DEFAULT_STAGING_DIR})"
        ),
    )
    parser.add_argument(
        "--show-unsupported",
        action="store_true",
        help="list packages that are pinned or do not yet have an update policy",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--workers", type=int, default=8, help="concurrent update checks (default: 8)"
    )
    parser.add_argument(
        "--downloads-file",
        type=pathlib.Path,
        default=DOWNLOADS_PATH,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    downloads = load_downloads(args.downloads_file)
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.write and not args.packages:
        parser.error("--write requires at least one PACKAGE")
    if args.write:
        requested = set(args.packages)
        tcl_tk = {"tcl", "tk"}
        if requested & tcl_tk and not tcl_tk <= requested:
            parser.error("--write must select tcl and tk together")

    packages = (
        validate_package_names(parser, args.packages, downloads)
        if args.packages
        else sorted(downloads.keys() & POLICIES.keys())
    )
    client = HttpClient(os.environ.get("GITHUB_TOKEN"))
    results = find_updates(downloads, packages, client, args.workers)

    if args.json:
        output: dict[str, Any] = {
            "results": [dataclasses.asdict(result) for result in results]
        }
        if args.show_unsupported:
            output["unsupported"] = {
                name: UNSUPPORTED.get(name, "no update policy")
                for name in sorted(downloads.keys() - POLICIES.keys())
            }
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        for result in results:
            if result.error:
                print(f"{result.package}: error: {result.error}", file=sys.stderr)
            elif result.release:
                marker = " (mirrored)" if POLICIES[result.package].mirrored else ""
                print(
                    f"{result.package}: {result.current_version} -> "
                    f"{result.release.version}{marker}\n  {result.release.url}"
                )
            else:
                print(f"{result.package}: {result.current_version} (current)")
        if args.show_unsupported:
            for name in sorted(downloads.keys() - POLICIES.keys()):
                reason = UNSUPPORTED.get(name, "no update policy")
                print(f"{name}: not checked ({reason})")

    changes: dict[str, dict[str, Any]] = {}
    staged: dict[str, tuple[pathlib.Path, Release, str]] = {}
    if args.write:
        for result in results:
            if not result.release or result.error:
                continue
            print(
                f"downloading {result.package} {result.release.version}",
                file=sys.stderr,
            )
            if POLICIES[result.package].mirrored:
                path, size, sha256 = stage_artifact(
                    client, result.release.url, args.staging_dir
                )
                staged[result.package] = (path, result.release, sha256)
            else:
                size, sha256 = artifact_metadata(client, result.release.url)
            changes[result.package] = {
                "url": stored_url(
                    result.release,
                    POLICIES[result.package],
                    args.upstream_urls,
                ),
                "size": size,
                "sha256": sha256,
                "version": result.release.version,
            }
        if changes:
            update_download_literals(
                args.downloads_file,
                changes,
                {
                    result.package: (result.release.url, not args.upstream_urls)
                    for result in results
                    if result.release
                    and result.package in changes
                    and POLICIES[result.package].mirrored
                },
            )
            if "openssl-3.5" in changes:
                update_openssl_disttest_version(changes["openssl-3.5"]["version"])
            print(
                f"updated {args.downloads_file}: {', '.join(sorted(changes))}",
                file=sys.stderr,
            )
            if "openssl-3.5" in changes:
                print(f"updated {DISTTESTS_PATH}", file=sys.stderr)
            print_mirror_instructions(staged)

    return 1 if any(result.error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
