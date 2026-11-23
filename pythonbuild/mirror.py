# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stage and verify release artifacts for the Astral mirror.

This mirrors the exact filenames referenced by ``dist/SHA256SUMS``. That file is
written by the GitHub release upload step, so using it here keeps the mirror in
lock-step with the GitHub Release contents without duplicating the Rust release
matrix logic in Python.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

BUILD_DATETIME_RE = re.compile(r"-(\d{8}T\d{4})\.tar\.(?:gz|zst)$")
DESTINATION_TAG_RE_TEMPLATE = r"^(cpython-[^+-]+)\+{tag}-(.+)$"


class MirrorError(RuntimeError):
    """Raised when release artifacts cannot be staged or verified."""


@dataclass(frozen=True)
class UploadEntry:
    source_name: str
    dest_name: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage and verify release distributions for the Astral mirror"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="Stage build outputs under release names")
    stage.add_argument(
        "--dist", type=Path, required=True, help="Directory with release artifacts"
    )
    stage.add_argument("--tag", required=True, help="Release tag")
    stage.add_argument(
        "--stage-to",
        type=Path,
        required=True,
        help="Existing empty directory for mirror assets",
    )
    verify = commands.add_parser(
        "verify", help="Verify a complete set of mirror assets"
    )
    verify.add_argument(
        "directory", type=Path, help="Directory with archives and SHA256SUMS"
    )
    return parser.parse_args(argv)


def infer_build_datetime(dist_dir: Path) -> str:
    datetimes: set[str] = {
        match.group(1)
        for path in dist_dir.iterdir()
        if path.is_file()
        and path.name.startswith("cpython-")
        and (match := BUILD_DATETIME_RE.search(path.name)) is not None
    }

    if not datetimes:
        raise SystemExit(f"could not infer build datetime from {dist_dir}")
    if len(datetimes) != 1:
        values = ", ".join(sorted(datetimes))
        raise SystemExit(f"expected one build datetime in {dist_dir}; found: {values}")

    return datetimes.pop()


def parse_shasums(shasums_path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in shasums_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            digest, filename = line.split(maxsplit=1)
        except ValueError as e:
            raise MirrorError(f"malformed line in {shasums_path}: {line!r}") from e

        filename = filename.removeprefix("*")
        if Path(filename).name != filename or not filename.endswith(
            (".tar.gz", ".tar.zst")
        ):
            raise MirrorError(f"expected a release archive filename: {filename}")
        if filename in checksums:
            raise MirrorError(f"duplicate archive in {shasums_path}: {filename}")
        checksums[filename] = digest.lower()

    if not checksums:
        raise MirrorError(f"no archives listed in {shasums_path}")
    return checksums


def destination_to_source_name(dest_name: str, tag: str, build_datetime: str) -> str:
    pattern = DESTINATION_TAG_RE_TEMPLATE.format(tag=re.escape(tag))
    if (match := re.match(pattern, dest_name)) is None:
        raise MirrorError(
            f"release filename does not contain expected tag {tag}: {dest_name}"
        )

    source_name = f"{match.group(1)}-{match.group(2)}"

    if source_name.endswith("-full.tar.zst"):
        prefix = source_name.removesuffix("-full.tar.zst")
        return f"{prefix}-{build_datetime}.tar.zst"

    if source_name.endswith(".tar.gz"):
        prefix = source_name.removesuffix(".tar.gz")
        return f"{prefix}-{build_datetime}.tar.gz"

    raise MirrorError(f"unsupported release filename: {dest_name}")


def build_upload_entries(
    dist_dir: Path, tag: str
) -> tuple[list[UploadEntry], list[str]]:
    build_datetime = infer_build_datetime(dist_dir)
    dest_names = parse_shasums(dist_dir / "SHA256SUMS")

    uploads: list[UploadEntry] = []
    missing: list[str] = []

    for dest_name in dest_names:
        source_name = destination_to_source_name(dest_name, tag, build_datetime)
        if not (dist_dir / source_name).exists():
            missing.append(source_name)
            continue
        uploads.append(UploadEntry(source_name=source_name, dest_name=dest_name))

    return uploads, missing


def stage_mirror_assets(
    dist_dir: Path, stage_dir: Path, uploads: Sequence[UploadEntry]
) -> None:
    for entry in uploads:
        (stage_dir / entry.dest_name).hardlink_to(dist_dir / entry.source_name)

    (stage_dir / "SHA256SUMS").hardlink_to(dist_dir / "SHA256SUMS")


def verify_mirror_assets(directory: Path) -> None:
    manifest = directory / "SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise MirrorError("SHA256SUMS must be a regular file")
    checksums = parse_shasums(manifest)
    archives = {path.name: path for path in directory.iterdir() if path != manifest}
    missing = checksums.keys() - archives.keys()
    extra = archives.keys() - checksums.keys()
    if missing or extra:
        raise MirrorError(
            f"archives do not match SHA256SUMS (missing: {sorted(missing)}, extra: {sorted(extra)})"
        )

    for name, digest in checksums.items():
        archive = archives[name]
        if archive.is_symlink() or not archive.is_file():
            raise MirrorError(f"expected a regular archive file: {name}")
        with archive.open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if actual != digest:
            raise MirrorError(f"SHA-256 mismatch for {name}")

    print(f"verified {len(checksums)} release archives against SHA256SUMS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.command == "verify":
            verify_mirror_assets(args.directory)
            return 0

        uploads, missing = build_upload_entries(args.dist, args.tag)

        if missing:
            for filename in missing:
                print(f"missing release artifact: {filename}")
            raise SystemExit(f"missing {len(missing)} release artifacts")

        stage_mirror_assets(args.dist, args.stage_to, uploads)
        print(f"staged {len(uploads)} release artifacts and SHA256SUMS")
    except (MirrorError, OSError) as e:
        raise SystemExit(str(e)) from e

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
