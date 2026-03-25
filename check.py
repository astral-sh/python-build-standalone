#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(os.path.abspath(__file__)).parent


def run_command(command: list[str]) -> int:
    print("$ " + " ".join(command), flush=True)
    returncode = subprocess.run(
        command,
        cwd=ROOT,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    ).returncode
    print()
    return returncode


def run() -> None:
    parser = argparse.ArgumentParser(description="Check code.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix problems",
    )
    args = parser.parse_args()

    check_args = ["--fix"] if args.fix else []
    format_args = [] if args.fix else ["--check"]

    check_result = run_command(["uv", "run", "ruff", "check", *check_args])
    format_result = run_command(["uv", "run", "ruff", "format", *format_args])
    mypy_result = run_command(["uv", "run", "mypy"])

    if check_result + format_result + mypy_result:
        print("Checks failed!")
        sys.exit(1)

    print("Checks passed!")


if __name__ == "__main__":
    run()
