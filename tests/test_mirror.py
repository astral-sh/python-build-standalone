# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import io
import os
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest import mock

from boto3.s3.transfer import TransferConfig
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from pythonbuild.mirror import (
    CACHE_CONTROL,
    MirrorError,
    S3MirrorClient,
    UploadEntry,
    build_upload_entries,
    destination_to_source_name,
    main,
    make_s3_client,
)

FULL_SOURCE = "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
FULL_DEST = "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst"
FULL_SHA256 = sha256(b"full").hexdigest()
INSTALL_SHA256 = sha256(b"install").hexdigest()


class MirrorTests(unittest.TestCase):
    def test_make_s3_client_uses_single_uploads_below_threshold(self) -> None:
        with (
            mock.patch.dict("pythonbuild.mirror.os.environ", {}, clear=True),
            mock.patch("pythonbuild.mirror.boto3.session.Session"),
        ):
            _client, transfer_config = make_s3_client()

        self.assertEqual(transfer_config.multipart_threshold, 200 * 1024 * 1024)

    def test_destination_to_source_name_full_archive(self) -> None:
        self.assertEqual(
            destination_to_source_name(
                "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
                "20260324",
                "20260324T1200",
            ),
            "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst",
        )

    def test_destination_to_source_name_install_only_archive(self) -> None:
        self.assertEqual(
            destination_to_source_name(
                "cpython-3.13.2+20260324-x86_64-unknown-linux-gnu-freethreaded-install_only.tar.gz",
                "20260324",
                "20260324T1200",
            ),
            "cpython-3.13.2-x86_64-unknown-linux-gnu-freethreaded-install_only-20260324T1200.tar.gz",
        )

    def test_destination_to_source_name_rejects_wrong_tag(self) -> None:
        with self.assertRaises(MirrorError):
            destination_to_source_name(
                "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
                "20260325",
                "20260324T1200",
            )

    def test_build_upload_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            (dist / FULL_SOURCE).write_bytes(b"full")
            (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
            ).write_bytes(b"install")
            (dist / "SHA256SUMS").write_text(
                f"{FULL_SHA256}  {FULL_DEST}\n"
                f"{INSTALL_SHA256} *cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            uploads, missing = build_upload_entries(dist, "20260324")

            self.assertEqual(missing, [])
            self.assertEqual(
                uploads,
                [
                    UploadEntry(
                        source_name=FULL_SOURCE,
                        dest_name=FULL_DEST,
                        sha256=FULL_SHA256,
                    ),
                    UploadEntry(
                        source_name="cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz",
                        dest_name="cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz",
                        sha256=INSTALL_SHA256,
                    ),
                ],
            )

    def test_build_upload_entries_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            ).write_bytes(b"full")
            (dist / "SHA256SUMS").write_text(
                "abc  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst\n"
                "def  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            uploads, missing = build_upload_entries(dist, "20260324")

            self.assertEqual(len(uploads), 1)
            self.assertEqual(
                missing,
                [
                    "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
                ],
            )

    def test_main_reports_all_upload_errors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            full_path = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            )
            install_only_path = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
            )
            full_path.write_bytes(b"full")
            install_only_path.write_bytes(b"install")
            (dist / "SHA256SUMS").write_text(
                "abc  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst\n"
                "def  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            def fail_upload(bucket: str, key: str, path: Path, sha256: str) -> None:
                raise MirrorError(f"failed for {path.name}")

            client = mock.Mock()
            client.get_paginator.return_value.paginate.return_value = []
            with (
                mock.patch(
                    "pythonbuild.mirror.make_s3_client",
                    return_value=(client, TransferConfig()),
                ),
                mock.patch.object(
                    S3MirrorClient,
                    "upload_file",
                    side_effect=fail_upload,
                ) as upload_file,
            ):
                with self.assertRaises(SystemExit) as cm:
                    main(
                        [
                            "--dist",
                            str(dist),
                            "--tag",
                            "20260324",
                            "--bucket",
                            "bucket",
                            "--prefix",
                            "prefix/",
                        ]
                    )

            self.assertEqual(
                str(cm.exception),
                "encountered 2 upload errors:\n"
                f"- failed for {install_only_path.name}\n"
                f"- failed for {full_path.name}",
            )
            self.assertEqual(upload_file.call_count, 2)


class MirrorUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dist = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.dist / FULL_SOURCE
        self.path.write_bytes(b"full")
        self.bucket = "bucket"
        self.prefix = "prefix/"
        self.key = self.prefix + FULL_DEST
        self.object_params = {"Bucket": self.bucket, "Key": self.key}
        self.put_params = {
            **self.object_params,
            "Body": ANY,
            "CacheControl": CACHE_CONTROL,
        }
        with mock.patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_DEFAULT_REGION": "us-east-1",
                "AWS_ENDPOINT_URL": "http://127.0.0.1:1",
                "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
            },
            clear=True,
        ):
            self.client, _ = make_s3_client()
        self.addCleanup(self.client.close)
        self.stubber = self.enterContext(Stubber(self.client))
        self.addCleanup(self.stubber.assert_no_pending_responses)
        self.transfer_config = TransferConfig(preferred_transfer_client="classic")
        self.mirror = S3MirrorClient(
            client=self.client,
            transfer_config=self.transfer_config,
            dry_run=False,
            existing_keys=set(),
        )

    def stub_locked_put(self, key: str) -> None:
        self.stubber.add_client_error(
            "put_object",
            "ObjectLockedByBucketPolicy",
            http_status_code=409,
            expected_params={**self.put_params, "Key": key},
        )

    def stub_get_object(self, key: str, data: bytes) -> io.BytesIO:
        stream = io.BytesIO(data)
        self.stubber.add_response(
            "get_object",
            {"Body": StreamingBody(stream, len(data))},
            {"Bucket": self.bucket, "Key": key},
        )
        return stream

    def test_recovers_locked_archive_and_manifest_after_listing_miss(self) -> None:
        manifest = f"{FULL_SHA256}  {FULL_DEST}\n".encode()
        (self.dist / "SHA256SUMS").write_bytes(manifest)
        # The release manifest is the source of truth for archive recovery.
        self.path.write_bytes(b"different staged bytes")
        self.stubber.add_response(
            "list_objects_v2", {}, {"Bucket": self.bucket, "Prefix": self.prefix}
        )
        streams = []
        for key, data in ((self.key, b"full"), (self.prefix + "SHA256SUMS", manifest)):
            self.stub_locked_put(key)
            streams.append(self.stub_get_object(key, data))

        with mock.patch(
            "pythonbuild.mirror.make_s3_client",
            return_value=(self.client, self.transfer_config),
        ):
            self.assertEqual(
                main(
                    [
                        "--dist",
                        str(self.dist),
                        "--tag",
                        "20260324",
                        "--bucket",
                        self.bucket,
                        "--prefix",
                        self.prefix,
                    ]
                ),
                0,
            )
        self.assertTrue(all(stream.closed for stream in streams))

    def test_locked_object_with_mismatched_bytes_fails(self) -> None:
        self.stub_locked_put(self.key)
        self.stub_get_object(self.key, b"wrong")

        with self.assertRaises(MirrorError) as cm:
            self.mirror.upload_file(self.bucket, self.key, self.path, FULL_SHA256)
        for detail in (self.key, FULL_SHA256, sha256(b"wrong").hexdigest()):
            self.assertIn(detail, str(cm.exception))

    def test_unrelated_conflict_is_not_reconciled(self) -> None:
        self.stubber.add_client_error(
            "put_object",
            "OperationAborted",
            http_status_code=409,
            expected_params=self.put_params,
        )

        with self.assertRaisesRegex(MirrorError, "OperationAborted"):
            self.mirror.upload_file(self.bucket, self.key, self.path, FULL_SHA256)

    def test_lock_recovery_fails_when_exact_key_is_missing(self) -> None:
        self.stub_locked_put(self.key)
        self.stubber.add_client_error(
            "get_object",
            "NoSuchKey",
            http_status_code=404,
            expected_params=self.object_params,
        )
        with self.assertRaisesRegex(MirrorError, "NoSuchKey"):
            self.mirror.upload_file(self.bucket, self.key, self.path, FULL_SHA256)

    def test_locked_multipart_completion_aborts_then_verifies(self) -> None:
        self.transfer_config.multipart_threshold = 1
        self.stubber.add_response("create_multipart_upload", {"UploadId": "upload-id"})
        upload_params = {**self.object_params, "UploadId": "upload-id"}
        self.stubber.add_response("upload_part", {"ETag": "part-etag"})
        self.stubber.add_client_error(
            "complete_multipart_upload",
            "ObjectLockedByBucketPolicy",
            http_status_code=409,
        )
        self.stubber.add_response("abort_multipart_upload", {}, upload_params)
        self.stub_get_object(self.key, b"full")

        self.mirror.upload_file(self.bucket, self.key, self.path, FULL_SHA256)


if __name__ == "__main__":
    unittest.main()
