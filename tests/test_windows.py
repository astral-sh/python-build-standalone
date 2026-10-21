# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "windows_build", ROOT / "cpython-windows" / "build.py"
)
assert SPEC is not None and SPEC.loader is not None
windows_build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(windows_build)


class WindowsBuildTests(unittest.TestCase):
    def test_dependency_architecture(self) -> None:
        for target, arch, dependency_arch in (
            ("i686", "x86", "x86"),
            ("x86_64", "amd64", "amd64"),
            ("aarch64", "arm64", "arm64"),
            ("arm64ec", "arm64ec", "amd64"),
        ):
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                triple = f"{target}-pc-windows-msvc"
                with ExitStack() as stack:
                    stack.enter_context(patch.object(windows_build, "BUILD", root))
                    stack.enter_context(
                        patch.object(windows_build, "DIST", root / "dist")
                    )
                    stack.enter_context(
                        patch.object(
                            windows_build.sys,
                            "argv",
                            [
                                "build.py",
                                "--target-triple",
                                triple,
                                "--python",
                                "cpython-3.14",
                                "--sh",
                                "sh.exe",
                            ],
                        )
                    )
                    mocks = {
                        name: stack.enter_context(patch.object(windows_build, name))
                        for name in (
                            "get_visual_studio_environment",
                            "fetch_strawberry_perl",
                            "build_openssl",
                            "build_libffi",
                            "build_cpython",
                            "compress_python_archive",
                            "release_tag_from_git",
                            "log",
                        )
                    }
                    mocks["get_visual_studio_environment"].return_value = {}
                    mocks["fetch_strawberry_perl"].return_value = root
                    mocks["build_cpython"].return_value = root / "python.tar"
                    windows_build.main()

                    mocks["get_visual_studio_environment"].assert_called_once_with(
                        "2022", dependency_arch, "14.4"
                    )
                    self.assertEqual(
                        mocks["build_openssl"].call_args.args[2], dependency_arch
                    )
                    self.assertEqual(
                        mocks["build_libffi"].call_args.args[1], dependency_arch
                    )
                    self.assertEqual(
                        mocks["build_cpython"].call_args.args[1:3], (triple, arch)
                    )

    def test_arm64ec_does_not_enable_x64_tail_call_interpreter(self) -> None:
        with patch.object(windows_build, "exec_and_log") as run:
            windows_build.run_msbuild(
                Path("MSBuild.exe"),
                Path("PCbuild"),
                "Release",
                "ARM64EC",
                "3.15.1",
                "10.0.26100.0",
                "v143",
                False,
            )
        args = run.call_args.args[0]
        self.assertIn("/property:Platform=ARM64EC", args)
        self.assertNotIn("/property:UseTailCallInterp=true", args)


if __name__ == "__main__":
    unittest.main()
