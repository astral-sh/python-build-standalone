# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stage release artifacts for the Astral mirror.

This mirrors the exact filenames referenced by ``dist/SHA256SUMS``. That file is
written by the GitHub release upload step, so using it here keeps the mirror in
lock-step with the GitHub Release contents without duplicating the Rust release
matrix logic in Python.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

BUILD_DATETIME_RE = re.compile(r"-(\d{8}T\d{4})\.tar\.(?:gz|zst)$")
DESTINATION_TAG_RE_TEMPLATE = r"^(cpython-[^+-]+)\+{tag}-(.+)$"


class MirrorError(RuntimeError):
    """Raised when release artifacts cannot be staged for the mirror."""


@dataclass(frozen=True)
class UploadEntry:
    source_name: str
    dest_name: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage release distributions for the Astral mirror"
    )
    parser.add_argument(
        "--dist", type=Path, required=True, help="Directory with release artifacts"
    )
    parser.add_argument("--tag", required=True, help="Release tag")
    parser.add_argument(
        "--stage-to",
        type=Path,
        required=True,
        help="Existing empty directory for mirror assets",
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


def parse_shasums(shasums_path: Path) -> list[str]:
    if not shasums_path.exists():
        raise SystemExit(f"{shasums_path} not found")

    filenames: list[str] = []
    for line in shasums_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            _digest, filename = line.split(maxsplit=1)
        except ValueError as e:
            raise SystemExit(f"malformed line in {shasums_path}: {line!r}") from e

        filenames.append(filename.lstrip("*"))

    return filenames


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
        if Path(entry.dest_name).name != entry.dest_name:
            raise MirrorError(f"expected a release filename: {entry.dest_name}")
        (stage_dir / entry.dest_name).hardlink_to(dist_dir / entry.source_name)

    (stage_dir / "SHA256SUMS").hardlink_to(dist_dir / "SHA256SUMS")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
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
