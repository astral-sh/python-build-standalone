# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "windows_build", ROOT / "cpython-windows" / "build.py"
)
windows_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows_build)

PATCH = b"""diff --git a/source.txt b/source.txt
--- a/source.txt
+++ b/source.txt
@@ -1,3 +1,3 @@
 before
-old
+new
 after
"""


class WindowsPatchTests(unittest.TestCase):
    def test_line_endings(self):
        for source_newline in (b"\n", b"\r\n"):
            for patch_newline in (b"\n", b"\r\n"):
                with self.subTest(source=source_newline, patch=patch_newline):
                    with tempfile.TemporaryDirectory() as td:
                        root = pathlib.Path(td)
                        source = root / "source tree"
                        source.mkdir()
                        target = source / "source.txt"
                        target.write_bytes(
                            source_newline.join([b"before", b"old", b"after", b""])
                        )
                        patch = root / "change.patch"
                        patch.write_bytes(PATCH.replace(b"\n", patch_newline))

                        windows_build.apply_source_patch(source, patch)

                        self.assertEqual(
                            target.read_bytes(), b"before\r\nnew\r\nafter\r\n"
                        )
                        self.assertFalse((source / ".git").exists())

    def test_failed_patch_does_not_apply_other_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = b"before\r\nold\r\nafter\r\n"
            (root / "source.txt").write_bytes(original)
            (root / "changed.txt").write_bytes(b"upstream changed\n")
            patch = root / "change.patch"
            patch.write_bytes(PATCH + PATCH.replace(b"source.txt", b"changed.txt"))

            with self.assertRaises(subprocess.CalledProcessError):
                windows_build.apply_source_patch(root, patch)

            self.assertEqual((root / "source.txt").read_bytes(), original)
            self.assertEqual((root / "changed.txt").read_bytes(), b"upstream changed\n")
            self.assertEqual(list(root.glob("*.rej")), [])

    def test_indentation_changes_are_not_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = b"before\r\n    old\r\nafter\r\n"
            (root / "source.txt").write_bytes(original)
            patch = root / "change.patch"
            patch.write_bytes(PATCH)

            with self.assertRaises(subprocess.CalledProcessError):
                windows_build.apply_source_patch(root, patch)

            self.assertEqual((root / "source.txt").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
