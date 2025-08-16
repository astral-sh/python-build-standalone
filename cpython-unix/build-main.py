#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import multiprocessing
import os
import pathlib
import subprocess
import sys

from pythonbuild.cpython import meets_python_minimum_version
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.utils import (
    compress_python_archive,
    current_host_platform,
    default_target_triple,
    get_target_settings,
    release_tag_from_git,
    supported_targets,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
SUPPORT = ROOT / "cpython-unix"
TARGETS_CONFIG = SUPPORT / "targets.yml"


def main():
    host_platform = current_host_platform()

    # Note these arguments must be synced with `build.py`
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target-triple",
        default=default_target_triple(),
        choices=supported_targets(TARGETS_CONFIG),
        help="Target host triple to build for",
    )

    # Construct possible options, we use a set here for canonical ordering
    options = set()
    options.update({"debug", "noopt", "pgo", "lto", "pgo+lto"})
    options.update({f"freethreaded+{option}" for option in options})
    options.update({f"{option}+static" for option in options})
    parser.add_argument(
        "--options",
        choices=options,
        default="noopt",
        help="Build options to apply when compiling Python",
    )
    parser.add_argument(
        "--python",
        choices={
            "cpython-3.9",
            "cpython-3.10",
            "cpython-3.11",
            "cpython-3.12",
            "cpython-3.13",
            "cpython-3.14",
        },
        default="cpython-3.11",
        help="Python distribution to build",
    )
    parser.add_argument(
        "--python-source",
        default=None,
        help="A custom path to CPython source files to use",
    )
    parser.add_argument(
        "--break-on-failure",
        action="store_true",
        help="Enter a Python debugger if an error occurs",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        default=True if sys.platform == "darwin" else False,
        help="Disable building in Docker",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Build packages serially, without parallelism",
    )
    parser.add_argument(
        "--make-target",
        choices={
            "default",
            "empty",
            "toolchain",
            "toolchain-image-build",
            "toolchain-image-build.cross",
            "toolchain-image-build.cross-riscv64",
            "toolchain-image-build.cross-loongarch64",
            "toolchain-image-build.debian9",
            "toolchain-image-gcc",
            "toolchain-image-xcb",
            "toolchain-image-xcb.cross",
            "toolchain-image-xcb.cross-riscv64",
        },
        default="default",
        help="The make target to evaluate",
    )

    args = parser.parse_args()

    target_triple = args.target_triple

    settings = get_target_settings(TARGETS_CONFIG, target_triple)

    supported_pythons = {"cpython-%s" % p for p in settings["pythons_supported"]}

    if args.python not in supported_pythons:
        print(
            "%s only supports following Pythons: %s"
            % (target_triple, ", ".join(supported_pythons))
        )
        return 1

    python_source = (
        (str(pathlib.Path(args.python_source).resolve()))
        if args.python_source
        else "null"
    )

    musl = "musl" in target_triple

    env = dict(os.environ)

    env["PYBUILD_HOST_PLATFORM"] = host_platform
    env["PYBUILD_TARGET_TRIPLE"] = target_triple
    env["PYBUILD_BUILD_OPTIONS"] = args.options
    env["PYBUILD_PYTHON_SOURCE"] = python_source
    if musl:
        env["PYBUILD_MUSL"] = "1"
    if args.break_on_failure:
        env["PYBUILD_BREAK_ON_FAILURE"] = "1"
    if args.no_docker:
        env["PYBUILD_NO_DOCKER"] = "1"

    if not args.python_source:
        entry = DOWNLOADS[args.python]
        env["PYBUILD_PYTHON_VERSION"] = cpython_version = entry["version"]
    else:
        # TODO consider parsing version from source checkout. Or defining version
        # from CLI argument.
        if "PYBUILD_PYTHON_VERSION" not in env:
            print("PYBUILD_PYTHON_VERSION must be set when using `--python-source`")
            return 1
        cpython_version = env["PYBUILD_PYTHON_VERSION"]

    python_majmin = ".".join(cpython_version.split(".")[0:2])

    if "PYBUILD_RELEASE_TAG" in os.environ:
        release_tag = os.environ["PYBUILD_RELEASE_TAG"]
    else:
        release_tag = release_tag_from_git()

    # Guard against accidental misuse of the free-threaded flag with older versions
    if "freethreaded" in args.options and not meets_python_minimum_version(
        python_majmin, "3.13"
    ):
        print(
            "Invalid build option: 'freethreaded' is only compatible with CPython 3.13+ (got %s)"
            % cpython_version
        )
        return 1

    archive_components = [
        "cpython-%s" % cpython_version,
        target_triple,
        args.options,
    ]

    build_basename = "-".join(archive_components) + ".tar"
    dist_basename = "-".join(archive_components + [release_tag])

    # We run make with static parallelism no greater than the machine's CPU count
    # because we can get some speedup from parallel operations. But we also don't
    # share a make job server with each build. So if we didn't limit the
    # parallelism we could easily oversaturate the CPU. Higher levels of
    # parallelism don't result in meaningful build speedups because tk has
    # a long, serial dependency chain that can't be built in parallel.
    parallelism = min(1 if args.serial else 4, multiprocessing.cpu_count())

    subprocess.run(
        ["make", "-j%d" % parallelism, args.make_target], env=env, check=True
    )

    DIST.mkdir(exist_ok=True)

    if args.make_target == "default":
        compress_python_archive(BUILD / build_basename, DIST, dist_basename)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
