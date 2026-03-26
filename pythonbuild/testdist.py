# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .utils import extract_python_archive


def run_dist_python(
    dist_root: Path,
    python_info,
    args: list[str],
    extra_env: Optional[dict[str, str]] = None,
    **runargs,
) -> subprocess.CompletedProcess[str]:
    """Runs a `python` process from an extracted PBS distribution.

    This function attempts to isolate the spawned interpreter from any
    external interference (PYTHON* environment variables), etc.
    """
    env = dict(os.environ)

    # Wipe PYTHON environment variables.
    for k in env:
        if k.startswith("PYTHON"):
            del env[k]

    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [str(dist_root / python_info["python_exe"])] + args,
        cwd=dist_root,
        env=env,
        **runargs,
    )


def run_custom_unittests(pbs_source_dir: Path, dist_root: Path, python_info) -> int:
    """Runs custom PBS unittests against a distribution."""

    args = [
        "-m",
        "unittest",
        "pythonbuild.disttests",
    ]

    env = {
        "PYTHONPATH": str(pbs_source_dir),
        "TARGET_TRIPLE": python_info["target_triple"],
        "BUILD_OPTIONS": python_info["build_options"],
    }

    res = run_dist_python(dist_root, python_info, args, env, stderr=subprocess.STDOUT)

    return res.returncode


def run_stdlib_tests(dist_root: Path, python_info, harness_args: list[str]) -> int:
    """Run Python stdlib tests for a PBS distribution.

    The passed path is the `python` directory from the extracted distribution
    archive.
    """
    args = [
        str(dist_root / python_info["run_tests"]),
    ]

    args.extend(harness_args)

    return run_dist_python(dist_root, python_info, args).returncode


def main(pbs_source_dir: Path, raw_args: list[str]) -> int:
    """test-distribution.py functionality."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--stdlib",
        action="store_true",
        help="Run the stdlib test harness",
    )
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

        codes = []

        codes.append(run_custom_unittests(pbs_source_dir, dist_path, python_info))

        if args.stdlib:
            codes.append(run_stdlib_tests(dist_path, python_info, args.harness_args))

        if len(codes) == 0:
            print("no tests run")
            return 1

        if any(code != 0 for code in codes):
            return 1

        return 0

    finally:
        if td:
            td.cleanup()
