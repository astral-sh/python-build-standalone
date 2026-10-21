# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import zstandard

from pythonbuild.utils import compress_python_archive


class ArchiveCompressionTests(unittest.TestCase):
    def test_compression_profiles_round_trip(self) -> None:
        contents = b"Python distribution archive\0" * 1024
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "python.tar"
            source.write_bytes(contents)
            for profile in ("small", "fast"):
                with self.subTest(profile=profile):
                    archive = compress_python_archive(
                        source, root, profile, compression=profile
                    )
                    self.assertEqual(
                        zstandard.ZstdDecompressor().decompress(archive.read_bytes()),
                        contents,
                    )
                    self.assertFalse(root.joinpath(f"{profile}.tar.zst.tmp").exists())

    def test_default_compression_is_small(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "python.tar"
            source.write_bytes(b"Python distribution archive\0" * 1024)
            default = compress_python_archive(source, root, "default")
            small = compress_python_archive(source, root, "small", compression="small")
            self.assertEqual(default.read_bytes(), small.read_bytes())


if __name__ == "__main__":
    unittest.main()
