#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import tarfile

from pythonbuild.downloads import DOWNLOADS

ROOT = pathlib.Path(__file__).resolve().parent
PATCHLEVEL_H = pathlib.Path("Include/patchlevel.h")
RELEASE_LEVEL_SUFFIX = {
    "PY_RELEASE_LEVEL_ALPHA": "a",
    "PY_RELEASE_LEVEL_BETA": "b",
    "PY_RELEASE_LEVEL_GAMMA": "rc",
    "PY_RELEASE_LEVEL_FINAL": "",
}


def read_cpython_version(source_dir: pathlib.Path) -> str:
    text = (source_dir / PATCHLEVEL_H).read_text()

    values: dict[str, str] = {}
    for name in (
        "PY_MAJOR_VERSION",
        "PY_MINOR_VERSION",
        "PY_MICRO_VERSION",
        "PY_RELEASE_LEVEL",
        "PY_RELEASE_SERIAL",
    ):
        m = re.search(rf"^#define {name}\s+(.+)$", text, re.MULTILINE)
        if not m:
            raise RuntimeError(f"could not find {name} in {source_dir / PATCHLEVEL_H}")

        values[name] = m.group(1).strip()

    suffix = RELEASE_LEVEL_SUFFIX[values["PY_RELEASE_LEVEL"]]
    version = (
        f"{values['PY_MAJOR_VERSION']}.{values['PY_MINOR_VERSION']}.{values['PY_MICRO_VERSION']}"
    )
    if suffix:
        version = f"{version}{suffix}{values['PY_RELEASE_SERIAL']}"

    return version


def create_archive(source_dir: pathlib.Path, archive_path: pathlib.Path, version: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    path_prefix = pathlib.PurePosixPath(f"Python-{version}")

    with archive_path.open("wb") as fh:
        with tarfile.open(name="", mode="w", fileobj=fh) as tf:
            for root, dirs, files in os.walk(source_dir):
                root_path = pathlib.Path(root)
                rel_root = root_path.relative_to(source_dir)

                dirs[:] = sorted(d for d in dirs if d != ".git")

                for name in sorted(files):
                    full = root_path / name
                    rel = rel_root / name if rel_root != pathlib.Path(".") else pathlib.Path(name)
                    tf.add(full, path_prefix / pathlib.PurePosixPath(rel.as_posix()))


def sha256_path(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def replace_download_entry(downloads_path: pathlib.Path, key: str, version: str, url: str, size: int, sha256: str) -> None:
    entry = DOWNLOADS[key]

    replacement = (
        f'    "{key}": {{\n'
        f'        "url": "{url}",\n'
        f'        "size": {size},\n'
        f'        "sha256": "{sha256}",\n'
        f'        "version": "{version}",\n'
        f'        "licenses": {json.dumps(entry["licenses"])},\n'
        f'        "license_file": "{entry["license_file"]}",\n'
        f'        "python_tag": "{entry["python_tag"]}",\n'
        f"    }},\n"
    )

    lines = downloads_path.read_text().splitlines(keepends=True)
    marker = f'    "{key}": {{\n'

    try:
        start = lines.index(marker)
    except ValueError as e:
        raise RuntimeError(f"could not find {key} in {downloads_path}") from e

    depth = 0
    end = None
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            end = i + 1
            break

    if end is None:
        raise RuntimeError(f"could not determine end of {key} entry in {downloads_path}")

    lines[start:end] = [replacement]
    downloads_path.write_text("".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, help="Python major.minor version, e.g. 3.14")
    parser.add_argument("--source-dir", required=True, type=pathlib.Path)
    parser.add_argument(
        "--downloads-file",
        default=ROOT / "pythonbuild" / "downloads.py",
        type=pathlib.Path,
    )
    parser.add_argument(
        "--archive-dir",
        default=ROOT / "build" / "downloads",
        type=pathlib.Path,
    )
    args = parser.parse_args()

    key = f"cpython-{args.python}"
    source_dir = args.source_dir.resolve()
    version = read_cpython_version(source_dir)

    if ".".join(version.split(".")[:2]) != args.python:
        raise RuntimeError(
            f"expected {source_dir} to be CPython {args.python}.x; got {version}"
        )

    archive_path = (args.archive_dir / f"Python-{version}.tar.xz").resolve()
    create_archive(source_dir, archive_path, version)

    size = archive_path.stat().st_size
    sha256 = sha256_path(archive_path)
    url = archive_path.as_uri()

    replace_download_entry(args.downloads_file, key, version, url, size, sha256)

    print(f"Prepared {key} from {source_dir}")
    print(f"  version: {version}")
    print(f"  archive: {archive_path}")
    print(f"  sha256: {sha256}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
