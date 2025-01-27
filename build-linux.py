#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import subprocess
import sys
import venv

ROOT = pathlib.Path(os.path.abspath(__file__)).parent
BUILD = ROOT / "build"
VENV = BUILD / "venv.linux"
PIP = VENV / "bin" / "pip"
PYTHON = VENV / "bin" / "python"
REQUIREMENTS = ROOT / "requirements.txt"
MAKE_DIR = ROOT / "cpython-unix"


def bootstrap():
    BUILD.mkdir(exist_ok=True)

    venv.create(VENV, with_pip=True, symlinks=True)

    subprocess.run([str(PIP), "install", "-r", str(REQUIREMENTS)], check=True)

    os.environ["PYBUILD_BOOTSTRAPPED"] = "1"
    os.environ["PATH"] = "%s:%s" % (str(VENV / "bin"), os.environ["PATH"])
    os.environ["PYTHONPATH"] = str(ROOT)

    args = [str(PYTHON), __file__, *sys.argv[1:]]

    os.execv(str(PYTHON), args)


def run():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    args = [
        str(PYTHON),
        "build-main.py",
        *sys.argv[1:],
    ]

    os.chdir(MAKE_DIR)
    os.execve(str(PYTHON), args, env)


if __name__ == "__main__":
    try:
        if "PYBUILD_BOOTSTRAPPED" not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
