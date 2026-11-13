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
import hashlib
import os
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client as Boto3S3Client

CACHE_CONTROL = "public, max-age=31536000, immutable"
UPLOAD_CONCURRENCY = 4
MAX_ATTEMPTS = 5
# R2 recommends multipart uploads above approximately 100 MB, but single uploads
# support objects up to about 5 GiB. Current release artifacts fit under 200 MiB.
# Single uploads avoid multipart completion for current artifacts, but a failed
# upload must retransmit the entire file. If R2 stores an object and its response
# is lost, retrying the same immutable key can still fail. Files at or above this
# threshold use multipart uploads and require additional retry handling.
# https://developers.cloudflare.com/r2/objects/upload-objects/#choose-an-upload-method
SINGLE_UPLOAD_THRESHOLD = 200 * 1024 * 1024
BUILD_DATETIME_RE = re.compile(r"-(\d{8}T\d{4})\.tar\.(?:gz|zst)$")
DESTINATION_TAG_RE_TEMPLATE = r"^(cpython-[^+-]+)\+{tag}-(.+)$"


class MirrorError(RuntimeError):
    """Base exception for mirror upload failures."""


@dataclass(frozen=True)
class UploadEntry:
    source_name: str
    dest_name: str
    sha256: str


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


def parse_shasums(shasums_path: Path) -> list[tuple[str, str]]:
    if not shasums_path.exists():
        raise SystemExit(f"{shasums_path} not found")

    checksums: list[tuple[str, str]] = []
    for line in shasums_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            digest, filename = line.split(maxsplit=1)
        except ValueError as e:
            raise SystemExit(f"malformed line in {shasums_path}: {line!r}") from e

        checksums.append((filename.lstrip("*"), digest.lower()))

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
    checksums = parse_shasums(dist_dir / "SHA256SUMS")

    uploads: list[UploadEntry] = []
    missing: list[str] = []

    for dest_name, sha256 in checksums:
        source_name = destination_to_source_name(dest_name, tag, build_datetime)
        if not (dist_dir / source_name).exists():
            missing.append(source_name)
            continue
        uploads.append(
            UploadEntry(source_name=source_name, dest_name=dest_name, sha256=sha256)
        )

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
            # The lock recovery check uses the manifest's full-object SHA-256.
            response_checksum_validation="when_required",
        )
    }
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    if region_name:
        client_kwargs["region_name"] = region_name

    session = boto3.session.Session()
    client: Boto3S3Client = session.client("s3", **client_kwargs)
    transfer_config = TransferConfig(
        multipart_threshold=SINGLE_UPLOAD_THRESHOLD,
    )

    return client, transfer_config


@dataclass(kw_only=True)
class S3MirrorClient:
    client: Boto3S3Client | None
    transfer_config: TransferConfig | None
    dry_run: bool
    existing_keys: set[str]

    def upload_file(
        self, bucket: str, key: str, path: Path, sha256: str | None = None
    ) -> None:
        if key in self.existing_keys:
            print(f"skipping existing s3://{bucket}/{key}")
            return

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
            # boto3 wraps the original ClientError in upload_file().
            error = e
            if isinstance(e, S3UploadFailedError):
                error = e.__cause__ or e.__context__
            if (
                isinstance(error, ClientError)
                and error.operation_name in ("PutObject", "CompleteMultipartUpload")
                and error.response.get("Error", {}).get("Code")
                == "ObjectLockedByBucketPolicy"
            ):
                self._verify_locked_object(self.client, bucket, key, path, sha256)
                return
            raise MirrorError(f"failed to upload {path.name}: {e}") from e

    @staticmethod
    def _verify_locked_object(
        client: Boto3S3Client, bucket: str, key: str, path: Path, sha256: str | None
    ) -> None:
        try:
            # SHA256SUMS has no entry for itself.
            if sha256 is None:
                with path.open("rb") as local:
                    sha256 = hashlib.file_digest(local, "sha256").hexdigest()

            response = client.get_object(Bucket=bucket, Key=key)
            digest = hashlib.sha256()
            with closing(response["Body"]) as body:
                for chunk in body.iter_chunks(1024 * 1024):
                    digest.update(chunk)
        except Exception as e:
            raise MirrorError(
                f"failed to verify locked object s3://{bucket}/{key}: {e}"
            ) from e

        actual = digest.hexdigest()
        if actual != sha256:
            raise MirrorError(
                f"SHA-256 mismatch for s3://{bucket}/{key}: expected {sha256}, got {actual}"
            )
        print(f"verified existing s3://{bucket}/{key}")


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
        existing_keys: set[str] = set()
        if not args.dry_run:
            client, transfer_config = make_s3_client()
            pages = client.get_paginator("list_objects_v2").paginate(
                Bucket=args.bucket, Prefix=args.prefix
            )
            existing_keys = {
                obj["Key"] for page in pages for obj in page.get("Contents", [])
            }

        mirror = S3MirrorClient(
            client=client,
            transfer_config=transfer_config,
            dry_run=args.dry_run,
            existing_keys=existing_keys,
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
                    entry.sha256,
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
