#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import platform
import subprocess
import sys
import venv

ROOT = pathlib.Path(os.path.abspath(__file__)).parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
VENV = BUILD / "venv"
PIP = VENV / "Scripts" / "pip.exe"
PYTHON = VENV / "Scripts" / "python.exe"
ARCH = "-arm64" if platform.machine() == "ARM64" else ""
REQUIREMENTS = ROOT / f"requirements.win{ARCH}.txt"
WINDOWS_DIR = ROOT / "cpython-windows"


def bootstrap():
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)

    venv.create(VENV, with_pip=True)

    subprocess.run([str(PIP), "install", "-r", str(REQUIREMENTS)], check=True)

    os.environ["PYBUILD_BOOTSTRAPPED"] = "1"
    os.environ["PATH"] = "%s;%s" % (str(VENV / "bin"), os.environ["PATH"])
    os.environ["PYTHONPATH"] = str(ROOT)
    args = [str(PYTHON), __file__]
    args.extend(sys.argv[1:])
    subprocess.run(args, check=True)


def run():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    args = [str(PYTHON), "build.py"]
    args.extend(sys.argv[1:])

    subprocess.run(args, cwd=str(WINDOWS_DIR), env=env, check=True, bufsize=0)


if __name__ == "__main__":
    try:
        if "PYBUILD_BOOTSTRAPPED" not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
