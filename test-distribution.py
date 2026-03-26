#!/usr/bin/env -S uv run
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Script to run Python tests from a distribution archive."""

import os
import pathlib
import sys

from pythonbuild.testdist import main

ROOT = pathlib.Path(os.path.abspath(__file__)).parent

if __name__ == "__main__":
    # Unbuffer stdout.
    sys.stdout.reconfigure(line_buffering=True)

    try:
        sys.exit(main(ROOT, sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(1)
