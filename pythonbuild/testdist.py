# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from .utils import extract_python_archive


def run_stdlib_tests(dist_root: Path, python_info, harness_args: list[str]) -> int:
    """Run Python stdlib tests for a PBS distribution.

    The passed path is the `python` directory from the extracted distribution
    archive.
    """
    args = [
        str(dist_root / python_info["python_exe"]),
        str(dist_root / python_info["run_tests"]),
    ]

    args.extend(harness_args)

    return subprocess.run(args).returncode


def main(raw_args: list[str]) -> int:
    """test-distribution.py functionality."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "dist",
        nargs=1,
        help="Path to distribution to test",
    )
    parser.add_argument(
        "harness_args",
        nargs=argparse.REMAINDER,
        help="Raw arguments to pass to Python's test harness",
    )

    args = parser.parse_args(raw_args)

    dist_path_raw = Path(args.dist[0])

    td = None
    try:
        if dist_path_raw.is_file():
            td = tempfile.TemporaryDirectory()
            dist_path = extract_python_archive(dist_path_raw, Path(td.name))
        else:
            dist_path = dist_path_raw

        python_json = dist_path / "PYTHON.json"

        with python_json.open("r", encoding="utf-8") as fh:
            python_info = json.load(fh)

        return run_stdlib_tests(dist_path, python_info, args.harness_args)
    finally:
        if td:
            td.cleanup()
