# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("make"), "make is required")
class PrebuiltHostPythonTests(unittest.TestCase):
    def test_target_build_still_builds_autoconf_and_m4(self) -> None:
        source = Path(__file__).resolve().parents[1] / "cpython-unix" / "Makefile"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            support = root / "cpython-unix"
            build = root / "build"
            support.mkdir()
            (build / "versions").mkdir(parents=True)
            (build / "targets").mkdir()
            shutil.copyfile(source, support / "Makefile")
            (build / "Makefile.linux_x86_64.x86_64-unknown-linux-gnu").write_text(
                "NEED_AUTOCONF := 1\n"
                "NEED_M4 := 1\n"
                "DOCKER_IMAGE_BUILD := build.debian13-x86_64\n"
                "CLANG_FILENAME := clang-test.tar\n"
                "CPYTHON_3.14_VERSION := 3.14.9\n"
                "AUTOCONF_VERSION := 2.72\n"
                "M4_VERSION := 1.4.20\n"
            )
            for path in (
                support / "setup-llvm-aliases.sh",
                support / "build-cpython.sh",
                support / "build-autoconf.sh",
                support / "build-m4.sh",
                build / "versions" / "VERSION.pip",
                build / "versions" / "VERSION.setuptools",
                build / "targets" / "x86_64-unknown-linux-gnu",
                build / "clang-test.tar",
                build / "build.debian13-x86_64.Dockerfile",
                build / "image-build.debian13-x86_64.linux_x86_64.tar",
                build / "cpython-3.14-3.14.9-linux_x86_64-build.debian13-x86_64.tar",
            ):
                path.touch()

            result = subprocess.run(
                ["make", "--dry-run", "RUN_BUILD=true"],
                cwd=support,
                env=os.environ
                | {
                    "PYBUILD_HOST_PLATFORM": "linux_x86_64",
                    "PYBUILD_TARGET_TRIPLE": "x86_64-unknown-linux-gnu",
                    "PYBUILD_BUILD_OPTIONS": "pgo+lto",
                    "PYBUILD_PYTHON_SOURCE": "null",
                    "PYBUILD_PYTHON_VERSION": "3.14.9",
                    "PYBUILD_USE_PREBUILT_HOST_PYTHON": "1",
                },
                capture_output=True,
                text=True,
                check=True,
            )
            recipes = result.stdout.splitlines()
            self.assertIn("true --docker-image build.debian13-x86_64 m4", recipes)
            self.assertIn("true --docker-image build.debian13-x86_64 autoconf", recipes)
            self.assertIn(
                "true --docker-image build.debian13-x86_64 cpython-3.14", recipes
            )
            self.assertNotIn("cpython-3.14-host", result.stdout)


if __name__ == "__main__":
    unittest.main()
