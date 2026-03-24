#!/usr/bin/env -S uv run --group check
#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run_command(command: list[str]) -> int:
    print("$ " + " ".join(command))
    returncode = subprocess.run(
        command, stdout=sys.stdout, stderr=sys.stderr
    ).returncode
    print()
    return returncode


def run():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    parser = argparse.ArgumentParser(description="Check code.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix problems",
    )
    args = parser.parse_args()

    check_args = []
    format_args = []
    mypy_args = []

    if args.fix:
        check_args.append("--fix")
    else:
        format_args.append("--check")

    check_result = run_command(["ruff", "check"] + check_args)
    format_result = run_command(["ruff", "format"] + format_args)
    mypy_result = run_command(["mypy"] + mypy_args)

    if check_result + format_result + mypy_result:
        print("Checks failed!")
        sys.exit(1)
    else:
        print("Checks passed!")


if __name__ == "__main__":
    try:
        run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
