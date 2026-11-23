# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from pythonbuild.mirror import (
    MirrorError,
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

    def test_staging_rejects_missing_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            stage = dist / "stage"
            stage.mkdir()
            (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            ).write_bytes(b"full")
            (dist / "SHA256SUMS").write_text(
                "abc  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst\n"
                "def  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            with self.assertRaisesRegex(SystemExit, "missing 1 release artifacts"):
                main(
                    [
                        "stage",
                        "--dist",
                        str(dist),
                        "--tag",
                        "20260324",
                        "--stage-to",
                        str(stage),
                    ]
                )
            self.assertEqual(list(stage.iterdir()), [])

    def test_stage_mirror_assets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist = root / "dist"
            dist.mkdir()
            stage = root / "stage"
            stage.mkdir()

            full_archive = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            )
            install_archive = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
            )
            full_name = (
                "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst"
            )
            install_name = (
                "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz"
            )
            full_archive.write_bytes(b"full")
            install_archive.write_bytes(b"install")
            manifest = dist / "SHA256SUMS"
            manifest.write_text(
                f"{sha256(b'full').hexdigest()}  {full_name}\n"
                f"{sha256(b'install').hexdigest()} *{install_name}\n"
            )

            self.assertEqual(
                main(
                    [
                        "stage",
                        "--dist",
                        str(dist),
                        "--tag",
                        "20260324",
                        "--stage-to",
                        str(stage),
                    ]
                ),
                0,
            )

            self.assertEqual(
                {path.name for path in stage.iterdir()},
                {full_name, install_name, "SHA256SUMS"},
            )
            self.assertTrue((stage / full_name).samefile(full_archive))
            self.assertTrue((stage / install_name).samefile(install_archive))
            self.assertTrue((stage / "SHA256SUMS").samefile(manifest))
            self.assertEqual(main(["verify", str(stage)]), 0)

    def test_verify_rejects_corrupt_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            archive = directory / "expected.tar.gz"
            archive.write_bytes(b"corrupt")
            digest = sha256(b"expected").hexdigest()
            (directory / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")

            with self.assertRaisesRegex(
                SystemExit, r"SHA-256 mismatch for expected\.tar\.gz"
            ):
                main(["verify", str(directory)])

    def test_verify_requires_exact_manifest_file_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory / "extra.tar.zst").write_bytes(b"extra")
            digest = sha256(b"expected").hexdigest()
            (directory / "SHA256SUMS").write_text(f"{digest}  expected.tar.gz\n")

            with self.assertRaisesRegex(
                SystemExit,
                r"archives do not match SHA256SUMS .*expected\.tar\.gz.*extra\.tar\.zst",
            ):
                main(["verify", str(directory)])

    def test_verify_rejects_paths_outside_download_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            digest = sha256(b"archive").hexdigest()
            (directory / "SHA256SUMS").write_text(f"{digest}  ../outside.tar.gz\n")

            with self.assertRaisesRegex(
                SystemExit, "expected a release archive filename"
            ):
                main(["verify", str(directory)])


if __name__ == "__main__":
    unittest.main()
