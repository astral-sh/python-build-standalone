# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Upload release artifacts to an S3-compatible mirror bucket.

This mirrors the exact filenames referenced by ``dist/SHA256SUMS``. That file is
written by the GitHub release upload step, so using it here keeps the mirror in
lock-step with the GitHub Release contents without duplicating the Rust release
matrix logic in Python.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from mypy_boto3_s3.client import S3Client as Boto3S3Client

CACHE_CONTROL = "public, max-age=31536000, immutable"
UPLOAD_CONCURRENCY = 4
MAX_ATTEMPTS = 5
BUILD_DATETIME_RE = re.compile(r"-(\d{8}T\d{4})\.tar\.(?:gz|zst)$")
DESTINATION_TAG_RE_TEMPLATE = r"^(cpython-[^+-]+)\+{tag}-(.+)$"


class MirrorError(RuntimeError):
    """Base exception for mirror upload failures."""


@dataclass(frozen=True)
class UploadEntry:
    source_name: str
    dest_name: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload release distributions to an S3-compatible mirror bucket"
    )
    parser.add_argument(
        "--dist", type=Path, required=True, help="Directory with release artifacts"
    )
    parser.add_argument("--tag", required=True, help="Release tag")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument(
        "--prefix",
        default="",
        help="Key prefix within the bucket (e.g. 'github/python-build-standalone/releases/download/20250317/')",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Dry run mode; do not actually upload",
    )
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Continue even if there are missing artifacts",
    )
    return parser.parse_args(argv)


def infer_build_datetime(dist_dir: Path) -> str:
    datetimes = {
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


def make_s3_client() -> tuple[Boto3S3Client, TransferConfig]:
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region_name = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
    if endpoint_url and region_name is None:
        region_name = "auto"

    client_kwargs: dict[str, Any] = {
        "config": Config(
            signature_version="s3v4",
            retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
            s3={"addressing_style": "path"},
        )
    }
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    if region_name:
        client_kwargs["region_name"] = region_name

    session = boto3.session.Session()
    client = session.client("s3", **client_kwargs)
    transfer_config = TransferConfig()

    return client, transfer_config


@dataclass(kw_only=True)
class S3MirrorClient:
    client: Boto3S3Client | None
    transfer_config: TransferConfig | None
    dry_run: bool

    def upload_file(self, bucket: str, key: str, path: Path) -> None:
        print(f"uploading {path.name} -> s3://{bucket}/{key}")
        if self.dry_run:
            return

        if self.client is None or self.transfer_config is None:
            raise MirrorError("S3 client not initialised")

        try:
            self.client.upload_file(
                str(path),
                bucket,
                key,
                ExtraArgs={"CacheControl": CACHE_CONTROL},
                Config=self.transfer_config,
            )
        except Exception as e:
            raise MirrorError(f"failed to upload {path.name}: {e}") from e


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        uploads, missing = build_upload_entries(args.dist, args.tag)

        for filename in missing:
            print(f"missing release artifact: {filename}")

        if missing and not args.ignore_missing:
            raise SystemExit(f"missing {len(missing)} release artifacts")

        if not missing:
            print(f"found all {len(uploads)} release artifacts")

        client = None
        transfer_config = None
        if not args.dry_run:
            client, transfer_config = make_s3_client()

        mirror = S3MirrorClient(
            client=client,
            transfer_config=transfer_config,
            dry_run=args.dry_run,
        )

        errors: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=UPLOAD_CONCURRENCY
        ) as executor:
            futures = [
                executor.submit(
                    mirror.upload_file,
                    args.bucket,
                    f"{args.prefix}{entry.dest_name}",
                    args.dist / entry.source_name,
                )
                for entry in uploads
            ]

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except MirrorError as e:
                    errors.append(str(e))

        if errors:
            error_lines = "\n".join(f"- {error}" for error in sorted(errors))
            raise MirrorError(
                f"encountered {len(errors)} upload errors:\n{error_lines}"
            )

        mirror.upload_file(
            args.bucket,
            f"{args.prefix}SHA256SUMS",
            args.dist / "SHA256SUMS",
        )
    except MirrorError as e:
        raise SystemExit(str(e)) from e

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
