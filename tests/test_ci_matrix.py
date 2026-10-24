# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ci_matrix", Path(__file__).resolve().parents[1] / "ci-matrix.py"
)
assert spec is not None and spec.loader is not None
ci_matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_matrix)


class HostPythonMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runners = {
            "x86": {"arch": "x86_64"},
            "arm": {"arch": "aarch64"},
        }
        self.settings = {
            "host_platforms": ["linux_x86_64", "linux_aarch64"],
            "host_cc": "clang",
            "host_cxx": "clang++",
            "host_ldflags": ["-fuse-ld=lld"],
            "needs_toolchain": True,
            "docker_image_suffix": ".debian13",
        }
        self.targets = {
            "target-a": self.settings,
            "target-b": copy.deepcopy(self.settings),
        }
        self.entries = [
            {
                "platform": "linux",
                "runner": "x86",
                "python": "3.14",
                "target_triple": "target-a",
                "build_options": "noopt",
            },
            {
                "platform": "linux",
                "runner": "x86",
                "python": "3.14",
                "target_triple": "target-b",
                "build_options": "freethreaded+pgo+lto+static",
            },
        ]

    def test_target_variants_share_a_host_build(self) -> None:
        producers = ci_matrix.generate_host_python_matrix_entries(
            self.entries, self.runners, self.targets
        )
        self.assertEqual(len(producers), 1)
        self.assertEqual(
            {entry["host_python_artifact"] for entry in self.entries},
            {producers[0]["host_python_artifact"]},
        )

    def test_different_host_inputs_are_isolated(self) -> None:
        variants = {
            "docker_image_suffix": ".cross",
            "host_cc": "gcc",
            "host_cxx": "g++",
            "host_ldflags": [],
            "needs_toolchain": False,
        }
        for key, value in variants.items():
            with self.subTest(setting=key):
                targets = copy.deepcopy(self.targets)
                targets["target-b"][key] = value
                producers = ci_matrix.generate_host_python_matrix_entries(
                    self.entries, self.runners, targets
                )
                self.assertEqual(len(producers), 2)
                self.assertNotEqual(
                    self.entries[0]["host_python_artifact"],
                    self.entries[1]["host_python_artifact"],
                )

    def test_python_versions_and_host_architectures_are_isolated(self) -> None:
        for key, value in [("python", "3.15"), ("runner", "arm")]:
            with self.subTest(setting=key):
                entries = copy.deepcopy(self.entries)
                entries[1][key] = value
                self.assertEqual(
                    len(
                        ci_matrix.generate_host_python_matrix_entries(
                            entries, self.runners, self.targets
                        )
                    ),
                    2,
                )

    def test_non_linux_entries_are_unchanged(self) -> None:
        entries = [{"platform": "windows"}, {"platform": "macos"}]
        original = copy.deepcopy(entries)
        self.assertEqual(
            ci_matrix.generate_host_python_matrix_entries(entries, {}, {}), []
        )
        self.assertEqual(entries, original)

    def test_dry_run_is_propagated(self) -> None:
        for entry in self.entries:
            entry["dry-run"] = "true"
        producers = ci_matrix.generate_host_python_matrix_entries(
            self.entries, self.runners, self.targets
        )
        self.assertEqual(producers[0]["dry-run"], "true")


if __name__ == "__main__":
    unittest.main()
