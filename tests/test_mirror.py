# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from boto3.s3.transfer import TransferConfig

from pythonbuild.mirror import (
    MirrorError,
    S3MirrorClient,
    UploadEntry,
    build_upload_entries,
    destination_to_source_name,
    main,
)


class MirrorTests(unittest.TestCase):
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
            (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            ).write_bytes(b"full")
            (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
            ).write_bytes(b"install")
            (dist / "SHA256SUMS").write_text(
                "abc  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst\n"
                "def  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            uploads, missing = build_upload_entries(dist, "20260324")

            self.assertEqual(missing, [])
            self.assertEqual(
                uploads,
                [
                    UploadEntry(
                        source_name="cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst",
                        dest_name="cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
                    ),
                    UploadEntry(
                        source_name="cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz",
                        dest_name="cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz",
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

            def fail_upload(bucket: str, key: str, path: Path) -> None:
                raise MirrorError(f"failed for {path.name}")

            with (
                mock.patch(
                    "pythonbuild.mirror.make_s3_client",
                    return_value=(object(), TransferConfig()),
                ),
                mock.patch.object(
                    S3MirrorClient,
                    "upload_file",
                    side_effect=fail_upload,
                ),
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


if __name__ == "__main__":
    unittest.main()
