#!/usr/bin/env -S uv run
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import platform
import subprocess
import sys

ROOT = pathlib.Path(os.path.abspath(__file__)).parent


def run():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    python = sys.executable
    system = platform.system()

    if system == "Darwin" or system == "Linux":
        args = [
            python,
            "build-main.py",
            *sys.argv[1:],
        ]
        make_dir = ROOT / "cpython-unix"
        os.chdir(make_dir)
        return os.execve(python, args, env)
    elif system == "Windows":
        args = [
            python,
            "build.py",
            *sys.argv[1:],
        ]
        cwd = str(ROOT / "cpython-windows")
        return subprocess.run(args, cwd=cwd, env=env, check=True, bufsize=0)
    else:
        raise Exception(f"Unsupported host system: {system}")


if __name__ == "__main__":
    try:
        run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
