#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import tempfile

import docker
import zstandard

from pythonbuild.buildenv import build_environment
from pythonbuild.cpython import (
    STDLIB_TEST_PACKAGES,
    derive_setup_local,
    extension_modules_config,
    meets_python_maximum_version,
    meets_python_minimum_version,
    parse_setup_line,
)
from pythonbuild.docker import build_docker_image, get_image, write_dockerfiles
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.logging import log, set_logger
from pythonbuild.utils import (
    add_env_common,
    add_licenses_to_extension_entry,
    clang_toolchain,
    create_tar_from_directory,
    download_entry,
    get_target_settings,
    get_targets,
    target_needs,
    validate_python_json,
    write_cpython_version,
    write_package_versions,
    write_target_settings,
    write_triples_makefiles,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DOWNLOADS_PATH = BUILD / "downloads"
SUPPORT = ROOT / "cpython-unix"
EXTENSION_MODULES = SUPPORT / "extension-modules.yml"
TARGETS_CONFIG = SUPPORT / "targets.yml"

LINUX_ALLOW_SYSTEM_LIBRARIES = {
    "c",
    "crypt",
    "dl",
    "m",
    "pthread",
    "rt",
    "util",
}
MACOS_ALLOW_SYSTEM_LIBRARIES = {"dl", "m", "pthread"}
MACOS_ALLOW_FRAMEWORKS = {"CoreFoundation"}


def install_sccache(build_env):
    """Attempt to install sccache into the build environment.

    This will attempt to locate a sccache executable and copy it
    into the root directory of the build environment.
    """
    candidates = [
        # Prefer a binary in the project itself.
        ROOT / "sccache",
    ]

    # Look for sccache in $PATH, but only if the build environment
    # isn't isolated, as copying binaries into an isolated environment
    # may not run. And running sccache in an isolated environment won't
    # do anything meaningful unless an external cache is being used.
    if not build_env.is_isolated:
        for path in os.environ.get("PATH", "").split(":"):
            if not path:
                continue

            candidates.append(pathlib.Path(path) / "sccache")

    for candidate in candidates:
        if candidate.exists():
            build_env.copy_file(candidate)
            return


def add_target_env(env, build_platform, target_triple, build_env):
    add_env_common(env)

    settings = get_target_settings(TARGETS_CONFIG, target_triple)

    env["TOOLCHAIN"] = "llvm"
    env["HOST_CC"] = settings["host_cc"]
    env["HOST_CXX"] = settings["host_cxx"]
    env["CC"] = settings["target_cc"]
    # We always set CXX, otherwise a build could bypass our toolchain
    # accidentally, e.g., on macOS where `g++` links to the system clang.
    env["CXX"] = settings["target_cxx"]

    if settings.get("bolt_capable"):
        env["BOLT_CAPABLE"] = "1"

    env["PYBUILD_PLATFORM"] = build_platform
    env["TOOLS_PATH"] = build_env.tools_path

    extra_target_cflags = list(settings.get("target_cflags", []))
    extra_target_ldflags = list(settings.get("target_ldflags", []))
    extra_host_cflags = []
    extra_host_ldflags = []

    if build_platform == "linux_x86_64":
        env["BUILD_TRIPLE"] = "x86_64-unknown-linux-gnu"

        env["TARGET_TRIPLE"] = (
            target_triple.replace("x86_64_v2-", "x86_64-")
            .replace("x86_64_v3-", "x86_64-")
            .replace("x86_64_v4-", "x86_64-")
        )

        # This will make x86_64_v2, etc count as cross-compiling. This is
        # semantically correct, since the current machine may not support
        # instructions on the target machine type.
        if env["BUILD_TRIPLE"] != target_triple or target_triple.endswith(
            "-unknown-linux-musl"
        ):
            env["CROSS_COMPILING"] = "1"

    if build_platform.startswith("macos_"):
        machine = platform.machine()

        if machine == "arm64":
            env["BUILD_TRIPLE"] = "aarch64-apple-darwin"
        elif machine == "x86_64":
            env["BUILD_TRIPLE"] = "x86_64-apple-darwin"
        else:
            raise Exception("unhandled macOS machine value: %s" % machine)

        # Sniff out the Apple SDK minimum deployment target from cflags and
        # export in its own variable. This is used by CPython's configure, as
        # it doesn't sniff the cflag.
        for flag in extra_target_cflags:
            m = re.search("-version-min=(.*)$", flag)
            if m:
                env["APPLE_MIN_DEPLOYMENT_TARGET"] = m.group(1)
                break
        else:
            raise Exception("could not find minimum Apple SDK version in cflags")

        sdk_platform = settings["apple_sdk_platform"]
        env["APPLE_SDK_PLATFORM"] = sdk_platform

        env["TARGET_TRIPLE"] = target_triple

        if env["BUILD_TRIPLE"] != env["TARGET_TRIPLE"]:
            env["CROSS_COMPILING"] = "1"

        # We don't have build isolation on macOS. We nerf PATH to prevent
        # non-system (e.g. Homebrew) executables from being used.
        env["PATH"] = "/usr/bin:/bin"

        if "APPLE_SDK_PATH" in os.environ:
            sdk_path = os.environ["APPLE_SDK_PATH"]
        else:
            # macOS SDK has historically been in /usr courtesy of an
            # installer provided by Xcode. But with Catalina, the files
            # are now typically in
            # /Applications/Xcode.app/Contents/Developer/Platforms/.
            # The proper way to resolve this path is with xcrun, which
            # will give us the headers that Xcode is configured to use.
            res = subprocess.run(
                ["xcrun", "--sdk", sdk_platform, "--show-sdk-path"],
                check=True,
                capture_output=True,
                encoding="utf-8",
            )

            sdk_path = res.stdout.strip()

        if not os.path.exists(sdk_path):
            raise Exception("macOS SDK path %s does not exist" % sdk_path)

        env["APPLE_SDK_PATH"] = sdk_path

        # Grab the version from the SDK so we can put it in PYTHON.json.
        sdk_settings_path = pathlib.Path(sdk_path) / "SDKSettings.json"
        with sdk_settings_path.open("rb") as fh:
            sdk_settings = json.load(fh)
            env["APPLE_SDK_VERSION"] = sdk_settings["Version"]
            env["APPLE_SDK_CANONICAL_NAME"] = sdk_settings["CanonicalName"]

        extra_target_cflags.extend(["-isysroot", sdk_path])
        extra_target_ldflags.extend(["-isysroot", sdk_path])

        # The host SDK may be for a different platform from the target SDK.
        # Resolve that separately.
        if "APPLE_HOST_SDK_PATH" in os.environ:
            host_sdk_path = os.environ["APPLE_HOST_SDK_PATH"]
        else:
            host_sdk_path = subprocess.run(
                ["xcrun", "--show-sdk-path"],
                check=True,
                capture_output=True,
                encoding="utf-8",
            ).stdout.strip()

        if not os.path.exists(host_sdk_path):
            raise Exception("macOS host SDK path %s does not exist" % host_sdk_path)

        extra_host_cflags.extend(["-isysroot", host_sdk_path])
        extra_host_ldflags.extend(["-isysroot", host_sdk_path])

    env["EXTRA_HOST_CFLAGS"] = " ".join(extra_host_cflags)
    env["EXTRA_HOST_LDFLAGS"] = " ".join(extra_host_ldflags)
    env["EXTRA_TARGET_CFLAGS"] = " ".join(extra_target_cflags)
    env["EXTRA_TARGET_LDFLAGS"] = " ".join(extra_target_ldflags)


def toolchain_archive_path(package_name, host_platform):
    entry = DOWNLOADS[package_name]

    basename = "%s-%s-%s.tar" % (package_name, entry["version"], host_platform)

    return BUILD / basename


def install_binutils(platform):
    return not platform.startswith("macos_")


def simple_build(
    settings,
    client,
    image,
    entry,
    host_platform,
    target_triple,
    build_options,
    dest_archive,
    extra_archives=None,
    tools_path="deps",
    python_host_version=None,
):
    archive = download_entry(entry, DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        if settings.get("needs_toolchain"):
            build_env.install_toolchain(
                BUILD,
                host_platform,
                target_triple,
                binutils=install_binutils(host_platform),
                clang=True,
                musl="musl" in target_triple,
                static="static" in build_options,
            )

        for a in extra_archives or []:
            build_env.install_artifact_archive(BUILD, a, target_triple, build_options)

        if python_host_version:
            majmin = ".".join(python_host_version.split(".")[0:2])
            build_env.install_toolchain_archive(
                BUILD,
                f"cpython-{majmin}",
                host_platform,
                version=python_host_version,
            )

        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / ("build-%s.sh" % entry))

        env = {
            "%s_VERSION" % entry.upper().replace("-", "_").replace(".", "_"): DOWNLOADS[
                entry
            ]["version"],
        }

        if "static" in build_options:
            env["STATIC"] = 1

        add_target_env(env, host_platform, target_triple, build_env)

        if entry in ("openssl-1.1", "openssl-3.0"):
            settings = get_targets(TARGETS_CONFIG)[target_triple]
            env["OPENSSL_TARGET"] = settings["openssl_target"]

        build_env.run("build-%s.sh" % entry, environment=env)

        build_env.get_tools_archive(dest_archive, tools_path)


def build_binutils(client, image, host_platform):
    """Build binutils in the Docker image."""
    archive = download_entry("binutils", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        install_sccache(build_env)

        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / "build-binutils.sh")

        env = {"BINUTILS_VERSION": DOWNLOADS["binutils"]["version"]}

        add_env_common(env)

        build_env.run(
            "build-binutils.sh",
            environment=env,
        )

        build_env.get_tools_archive(
            toolchain_archive_path("binutils", host_platform), "host"
        )


def materialize_clang(host_platform: str, target_triple: str):
    entry = clang_toolchain(host_platform, target_triple)
    tar_zst = download_entry(entry, DOWNLOADS_PATH)
    local_filename = "%s-%s-%s.tar" % (
        entry,
        DOWNLOADS[entry]["version"],
        host_platform,
    )

    dctx = zstandard.ZstdDecompressor()

    with open(tar_zst, "rb") as ifh:
        with open(BUILD / local_filename, "wb") as ofh:
            dctx.copy_stream(ifh, ofh)


def build_musl(client, image, host_platform: str, target_triple: str, build_options):
    static = "static" in build_options
    musl = "musl-static" if static else "musl"
    musl_archive = download_entry(musl, DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            target_triple,
            binutils=True,
            clang=True,
            static=False,
        )
        build_env.copy_file(musl_archive)
        build_env.copy_file(SUPPORT / "build-musl.sh")

        env = {
            "MUSL_VERSION": DOWNLOADS[musl]["version"],
            "TOOLCHAIN": "llvm",
        }

        if static:
            env["STATIC"] = 1

        build_env.run("build-musl.sh", environment=env)

        build_env.get_tools_archive(toolchain_archive_path(musl, host_platform), "host")


def build_libedit(
    settings, client, image, host_platform, target_triple, build_options, dest_archive
):
    libedit_archive = download_entry("libedit", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        if settings.get("needs_toolchain"):
            build_env.install_toolchain(
                BUILD,
                host_platform,
                target_triple,
                binutils=install_binutils(host_platform),
                clang=True,
                musl="musl" in target_triple,
                static="static" in build_options,
            )

        build_env.install_artifact_archive(
            BUILD, "ncurses", target_triple, build_options
        )
        build_env.copy_file(libedit_archive)
        build_env.copy_file(SUPPORT / "build-libedit.sh")

        env = {
            "LIBEDIT_VERSION": DOWNLOADS["libedit"]["version"],
        }

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-libedit.sh", environment=env)
        build_env.get_tools_archive(dest_archive, "deps")


def build_tix(
    settings, client, image, host_platform, target_triple, build_options, dest_archive
):
    tcl_archive = download_entry("tcl", DOWNLOADS_PATH)
    tk_archive = download_entry("tk", DOWNLOADS_PATH)
    tix_archive = download_entry("tix", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        if settings.get("needs_toolchain"):
            build_env.install_toolchain(
                BUILD,
                host_platform,
                target_triple,
                binutils=install_binutils(host_platform),
                clang=True,
                musl="musl" in target_triple,
                static="static" in build_options,
            )

        depends = {"tcl", "tk"}
        if not host_platform.startswith("macos_"):
            depends |= {"libX11", "xorgproto"}

        for p in sorted(depends):
            build_env.install_artifact_archive(BUILD, p, target_triple, build_options)

        for p in (tcl_archive, tk_archive, tix_archive, SUPPORT / "build-tix.sh"):
            build_env.copy_file(p)

        env = {
            "TOOLCHAIN": "clang-%s" % host_platform,
            "TCL_VERSION": DOWNLOADS["tcl"]["version"],
            "TIX_VERSION": DOWNLOADS["tix"]["version"],
            "TK_VERSION": DOWNLOADS["tk"]["version"],
        }

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-tix.sh", environment=env)
        build_env.get_tools_archive(dest_archive, "deps")


def build_cpython_host(
    client,
    image,
    entry,
    host_platform: str,
    target_triple: str,
    build_options: list[str],
    dest_archive,
):
    """Build binutils in the Docker image."""
    archive = download_entry(entry, DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        python_version = DOWNLOADS[entry]["version"]

        build_env.install_toolchain(
            BUILD,
            host_platform,
            target_triple,
            binutils=install_binutils(host_platform),
            clang=True,
            static="static" in build_options,
        )

        build_env.copy_file(archive)

        support = {
            "build-cpython-host.sh",
            "patch-disable-multiarch.patch",
            "patch-disable-multiarch-13.patch",
        }
        for s in sorted(support):
            build_env.copy_file(SUPPORT / s)

        packages = {
            "autoconf",
            "m4",
        }
        for p in sorted(packages):
            build_env.install_artifact_archive(BUILD, p, target_triple, build_options)

        env = {
            "PYTHON_VERSION": python_version,
        }

        add_target_env(env, host_platform, target_triple, build_env)

        # Set environment variables allowing convenient testing for Python
        # version ranges.
        for v in ("3.9", "3.10", "3.11", "3.12", "3.13", "3.14"):
            normal_version = v.replace(".", "_")

            if meets_python_minimum_version(python_version, v):
                env[f"PYTHON_MEETS_MINIMUM_VERSION_{normal_version}"] = "1"
            if meets_python_maximum_version(python_version, v):
                env[f"PYTHON_MEETS_MAXIMUM_VERSION_{normal_version}"] = "1"

        build_env.run(
            "build-cpython-host.sh",
            environment=env,
        )

        build_env.get_tools_archive(dest_archive, "host")


def python_build_info(
    build_env,
    version,
    platform,
    target_triple,
    musl,
    lto,
    static,
    extensions,
    extra_metadata,
):
    """Obtain build metadata for the Python distribution."""

    log("resolving Python distribution build info")

    bi = {"core": {"objs": [], "links": []}, "extensions": {}}

    binary_suffix = ""

    if platform == "linux_x86_64":
        bi["core"]["static_lib"] = (
            "install/lib/python{version}/config-{version}{binary_suffix}-x86_64-linux-gnu/libpython{version}{binary_suffix}.a".format(
                version=version, binary_suffix=binary_suffix
            )
        )

        if not static:
            bi["core"]["shared_lib"] = "install/lib/libpython%s%s.so.1.0" % (
                version,
                binary_suffix,
            )

        if lto:
            llvm_version = DOWNLOADS[clang_toolchain(platform, target_triple)][
                "version"
            ]
            if "+" in llvm_version:
                llvm_version = llvm_version.split("+")[0]

            object_file_format = f"llvm-bitcode:%{llvm_version}"
        else:
            object_file_format = "elf"
    elif platform.startswith("macos_"):
        bi["core"]["static_lib"] = (
            "install/lib/python{version}/config-{version}{binary_suffix}-darwin/libpython{version}{binary_suffix}.a".format(
                version=version, binary_suffix=binary_suffix
            )
        )
        bi["core"]["shared_lib"] = "install/lib/libpython%s%s.dylib" % (
            version,
            binary_suffix,
        )

        if lto:
            object_file_format = (
                "llvm-bitcode:%s" % DOWNLOADS["llvm-aarch64-macos"]["version"]
            )
        else:
            object_file_format = "mach-o"
    else:
        raise Exception("unsupported platform: %s" % platform)

    bi["object_file_format"] = object_file_format

    # Determine allowed libaries on Linux
    libs = extra_metadata["python_config_vars"].get("LIBS", "").split()
    mips = target_triple.split("-")[0] in {"mips", "mipsel"}
    linux_allowed_system_libraries = LINUX_ALLOW_SYSTEM_LIBRARIES.copy()
    if mips and version == "3.13":
        # See https://github.com/astral-sh/python-build-standalone/issues/410
        linux_allowed_system_libraries.add("atomic")
    riscv = target_triple.split("-")[0] in {"riscv64"}
    if riscv:
        # On older GCC versions, RISC-V sub-word atomic operations require a
        # helper function found in libatomic. To facilitate this, GCC <15 adds
        # "-latomic" to the definition of "-pthread". We think it's generally
        # reasonable on RISC-V systems (but not all Linux systems in general)
        # to expect a libatomic system library is installed.
        #
        # Because "-latomic" is implicitly added by "-pthread", it may not be
        # found in the LIBS sysconfig variable, but we need to pretend it is so
        # that it gets into PYTHON.json (in particular, so that the validation
        # script accepts this dependency).
        #
        # See https://github.com/riscvarchive/riscv-gcc/issues/12
        # https://github.com/riscvarchive/riscv-gcc/issues/337
        # https://gcc.gnu.org/bugzilla/show_bug.cgi?id=86005
        # https://gcc.gnu.org/bugzilla/show_bug.cgi?id=104338
        # https://github.com/gcc-mirror/gcc/commit/203f3060dd363361b172f7295f42bb6bf5ac0b3b
        linux_allowed_system_libraries.add("atomic")
        libs.append("-latomic")

    # Add in core linking annotations.
    skip = False
    for i, lib in enumerate(libs):
        if skip:
            skip = False
            continue

        if lib.startswith("-l"):
            lib = lib[2:]

            if platform == "linux_x86_64" and lib not in linux_allowed_system_libraries:
                raise Exception("unexpected library in LIBS (%s): %s" % (libs, lib))
            elif (
                platform.startswith("macos_")
                and lib not in MACOS_ALLOW_SYSTEM_LIBRARIES
            ):
                raise Exception("unexpected library in LIBS (%s): %s" % (libs, lib))

            log("adding core system link library: %s" % lib)
            bi["core"]["links"].append(
                {
                    "name": lib,
                    "system": True,
                }
            )
        elif lib == "-framework":
            skip = True
            framework = libs[i + 1]
            if framework not in MACOS_ALLOW_FRAMEWORKS:
                raise Exception(
                    "unexpected framework in LIBS (%s): %s" % (libs, framework)
                )

            log("adding core link framework: %s" % framework)
            bi["core"]["links"].append({"name": framework, "framework": True})
        else:
            raise Exception("unknown word in LIBS (%s): %s" % (libs, lib))

    # Object files for the core distribution are found by walking the
    # build artifacts.
    core_objs = set()
    modules_objs = set()

    for f in build_env.find_output_files("python/build", "*.o"):
        rel_path = pathlib.Path("build") / f

        if rel_path.parts[1] in ("Objects", "Parser", "Python"):
            core_objs.add(rel_path)

        if rel_path.parts[1] == "Modules":
            modules_objs.add(rel_path)

    for p in sorted(core_objs):
        log("adding core object file: %s" % p)
        bi["core"]["objs"].append(str(p))

    assert pathlib.Path("build/Modules/config.o") in modules_objs
    bi["inittab_object"] = "build/Modules/config.o"
    bi["inittab_source"] = "build/Modules/config.c"
    # TODO ideally we'd get these from the build environment
    bi["inittab_cflags"] = ["-std=c99", "-DNDEBUG", "-DPy_BUILD_CORE"]

    libraries = set()

    for f in build_env.find_output_files("python/build/lib", "*.a"):
        # Strip "lib" prefix and ".a" suffix.
        libname = f[3:-2]

        libraries.add(libname)

    for extension, info in sorted(extensions.items()):
        log(f"processing extension module {extension}")

        d = parse_setup_line(info["setup_line"], version)
        if not d:
            raise Exception(f"Setup line for {extension} failed to parse")

        objs = []

        for obj in sorted(d["posix_obj_paths"]):
            obj = pathlib.Path("build") / obj
            log("adding object file %s for extension %s" % (obj, extension))
            objs.append(str(obj))

            # Mark object file as used so we don't include it in the core
            # object files below. .remove() would be nicer, as we would catch
            # missing object files. But some sources (like math.c) are used by
            # multiple modules!
            modules_objs.discard(obj)

        links = []

        for framework in sorted(d["frameworks"]):
            log("adding framework %s for extension %s" % (framework, extension))
            links.append({"name": framework, "framework": True})

        for libname in sorted(d["links"]):
            # Explicitly annotated .a files are statically linked and don't need
            # annotations.
            if libname.endswith(".a"):
                continue

            log("adding library %s for extension %s" % (libname, extension))

            if libname in libraries:
                entry = {"name": libname, "path_static": "build/lib/lib%s.a" % libname}

                links.append(entry)
            else:
                links.append({"name": libname, "system": True})

        if targets := info.get("required-targets"):
            required = any(re.match(p, target_triple) for p in targets)
        else:
            required = False

        entry = {
            "in_core": info["in_core"],
            "init_fn": info["init_fn"],
            "links": links,
            "objs": objs,
            "required": required,
            "variant": d["variant"],
        }

        if info.get("build-mode") == "shared":
            shared_dir = extra_metadata["python_config_vars"]["DESTSHARED"].strip("/")
            extension_suffix = extra_metadata["python_config_vars"]["EXT_SUFFIX"]
            entry["shared_lib"] = "%s/%s%s" % (shared_dir, extension, extension_suffix)

        add_licenses_to_extension_entry(entry)

        bi["extensions"].setdefault(extension, []).append(entry)

    # Any paths left in modules_objs are not part of any extension and are
    # instead part of the core distribution.
    for p in sorted(modules_objs):
        log("adding core object file %s" % p)
        bi["core"]["objs"].append(str(p))

    return bi


def build_cpython(
    settings,
    client,
    image,
    host_platform,
    target_triple,
    build_options,
    dest_archive,
    version=None,
    python_source=None,
):
    """Build CPython in a Docker image'"""
    parsed_build_options = set(build_options.split("+"))
    entry_name = "cpython-%s" % version
    entry = DOWNLOADS[entry_name]
    if not python_source:
        python_version = entry["version"]
        python_archive = download_entry(entry_name, DOWNLOADS_PATH)
    else:
        python_version = os.environ["PYBUILD_PYTHON_VERSION"]
        python_archive = DOWNLOADS_PATH / ("Python-%s.tar.xz" % python_version)
        print("Compressing %s to %s" % (python_source, python_archive))
        with python_archive.open("wb") as fh:
            create_tar_from_directory(
                fh, python_source, path_prefix="Python-%s" % python_version
            )

    setuptools_archive = download_entry("setuptools", DOWNLOADS_PATH)
    pip_archive = download_entry("pip", DOWNLOADS_PATH)

    ems = extension_modules_config(EXTENSION_MODULES)

    setup = derive_setup_local(
        python_archive,
        python_version=python_version,
        target_triple=target_triple,
        build_options=parsed_build_options,
        extension_modules=ems,
    )

    enabled_extensions = setup["extensions"]
    setup_local_content = setup["setup_local"]
    extra_make_content = setup["make_data"]

    with build_environment(client, image) as build_env:
        if settings.get("needs_toolchain"):
            build_env.install_toolchain(
                BUILD,
                host_platform,
                target_triple,
                binutils=install_binutils(host_platform),
                clang=True,
                musl="musl" in target_triple,
                static="static" in build_options,
            )

        packages = target_needs(TARGETS_CONFIG, target_triple, python_version)
        # Toolchain packages are handled specially.
        packages.discard("binutils")
        packages.discard("musl")

        for p in sorted(packages):
            build_env.install_artifact_archive(BUILD, p, target_triple, build_options)

        # Install the host CPython.
        build_env.install_toolchain_archive(
            BUILD, entry_name, host_platform, version=python_version
        )

        for p in (
            python_archive,
            setuptools_archive,
            pip_archive,
            SUPPORT / "build-cpython.sh",
            SUPPORT / "run_tests-13.py",
        ):
            build_env.copy_file(p)

        for f in sorted(os.listdir(ROOT)):
            if f.startswith("LICENSE.") and f.endswith(".txt"):
                build_env.copy_file(ROOT / f)

        for f in sorted(os.listdir(SUPPORT)):
            if f.endswith(".patch"):
                build_env.copy_file(SUPPORT / f)

        with tempfile.NamedTemporaryFile("wb") as fh:
            # In case default file masks cause wonkiness.
            os.chmod(fh.name, 0o644)

            fh.write(setup_local_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Setup.local")

        with tempfile.NamedTemporaryFile("wb") as fh:
            os.chmod(fh.name, 0o644)
            fh.write(extra_make_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Makefile.extra")

        env = {
            "PIP_VERSION": DOWNLOADS["pip"]["version"],
            "PYTHON_VERSION": python_version,
            "PYTHON_MAJMIN_VERSION": ".".join(python_version.split(".")[0:2]),
            "SETUPTOOLS_VERSION": DOWNLOADS["setuptools"]["version"],
            "TOOLCHAIN": "clang-%s" % host_platform,
        }

        # Set environment variables allowing convenient testing for Python
        # version ranges.
        for v in ("3.9", "3.10", "3.11", "3.12", "3.13", "3.14"):
            normal_version = v.replace(".", "_")

            if meets_python_minimum_version(python_version, v):
                env[f"PYTHON_MEETS_MINIMUM_VERSION_{normal_version}"] = "1"
            if meets_python_maximum_version(python_version, v):
                env[f"PYTHON_MEETS_MAXIMUM_VERSION_{normal_version}"] = "1"

        if "freethreaded" in parsed_build_options:
            env["CPYTHON_FREETHREADED"] = "1"

        if "debug" in parsed_build_options:
            env["CPYTHON_DEBUG"] = "1"
        if "pgo" in parsed_build_options:
            env["CPYTHON_OPTIMIZED"] = "1"
        if "lto" in parsed_build_options:
            env["CPYTHON_LTO"] = "1"
        if "static" in parsed_build_options:
            env["CPYTHON_STATIC"] = "1"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-cpython.sh", environment=env)

        extension_module_loading = ["builtin"]
        crt_features = []

        if host_platform == "linux_x86_64":
            if "static" in parsed_build_options:
                crt_features.append("static")
            else:
                extension_module_loading.append("shared-library")

                if "musl" in target_triple:
                    crt_features.append("musl-dynamic")

                    musl_version = DOWNLOADS["musl"]["version"]
                    crt_features.append("musl-version:%s" % musl_version)

                else:
                    crt_features.append("glibc-dynamic")

                    glibc_max_version = build_env.get_file("glibc_version.txt").strip()
                    if not glibc_max_version:
                        raise Exception("failed to retrieve glibc max symbol version")

                    crt_features.append(
                        "glibc-max-symbol-version:%s"
                        % glibc_max_version.decode("ascii")
                    )

            python_symbol_visibility = "global-default"

        elif host_platform.startswith("macos_"):
            python_symbol_visibility = "global-default"
            extension_module_loading.append("shared-library")
            crt_features.append("libSystem")
        else:
            raise ValueError("unhandled platform: %s" % host_platform)

        extra_metadata = json.loads(build_env.get_file("metadata.json"))

        # TODO: Remove `optimizations` in the future, deprecated in favor of
        # `build_options` in metadata version 8.
        optimizations = build_options.replace("freethreaded+", "")

        # Create PYTHON.json file describing this distribution.
        python_info = {
            "version": "8",
            "target_triple": target_triple,
            "optimizations": optimizations,
            "build_options": build_options,
            "python_tag": entry["python_tag"],
            "python_version": python_version,
            "python_stdlib_test_packages": sorted(STDLIB_TEST_PACKAGES),
            "python_symbol_visibility": python_symbol_visibility,
            "python_extension_module_loading": extension_module_loading,
            "libpython_link_mode": (
                "static" if "static" in parsed_build_options else "shared"
            ),
            "crt_features": crt_features,
            "run_tests": "build/run_tests.py",
            "build_info": python_build_info(
                build_env,
                version,
                host_platform,
                target_triple,
                "musl" in target_triple,
                "lto" in parsed_build_options,
                "static" in parsed_build_options,
                enabled_extensions,
                extra_metadata,
            ),
            "licenses": entry["licenses"],
            "license_path": "licenses/LICENSE.cpython.txt",
        }

        python_info["tcl_library_path"] = "install/lib"
        python_info["tcl_library_paths"] = [
            "itcl4.2.4",
            "tcl8",
            "tcl8.6",
            "thread2.8.7",
            "tk8.6",
        ]

        if "-apple" not in target_triple:
            python_info["tcl_library_paths"].append("Tix8.4.3")

        if "-apple" in target_triple:
            python_info["apple_sdk_platform"] = env["APPLE_SDK_PLATFORM"]
            python_info["apple_sdk_version"] = env["APPLE_SDK_VERSION"]
            python_info["apple_sdk_canonical_name"] = env["APPLE_SDK_CANONICAL_NAME"]
            python_info["apple_sdk_deployment_target"] = env[
                "APPLE_MIN_DEPLOYMENT_TARGET"
            ]

        # Add metadata derived from built distribution.
        python_info.update(extra_metadata)

        validate_python_json(python_info, extension_modules=ems)

        with tempfile.NamedTemporaryFile("w") as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)
            fh.flush()

            if image:
                dest_path = "/build/out/python"
            else:
                dest_path = "out/python"

            build_env.copy_file(fh.name, dest_path, dest_name="PYTHON.json")

        with open(dest_archive, "wb") as fh:
            fh.write(build_env.get_output_archive("python"))


def main():
    BUILD.mkdir(exist_ok=True)
    DOWNLOADS_PATH.mkdir(exist_ok=True)
    (BUILD / "logs").mkdir(exist_ok=True)

    if os.environ.get("PYBUILD_NO_DOCKER"):
        client = None
    else:
        try:
            client = docker.from_env(timeout=600)
            client.ping()
        except Exception as e:
            print("unable to connect to Docker: %s" % e, file=sys.stderr)
            return 1

    # Note these arguments must be synced with `build-main.py`
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host-platform", required=True, help="Platform we are building from"
    )
    parser.add_argument(
        "--target-triple",
        required=True,
        help="Host triple that we are building Python for",
    )

    # Construct possible options
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
        "--toolchain",
        action="store_true",
        help="Indicates we are building a toolchain artifact",
    )
    parser.add_argument(
        "--dest-archive", required=True, help="Path to archive that we are producing"
    )
    parser.add_argument("--docker-image", help="Docker image to use for building")
    parser.add_argument(
        "--python-source",
        default=None,
        help="A custom path to CPython source files to use",
    )
    parser.add_argument(
        "--python-host-version",
        default=None,
        help="Python X.Y version for host Python installation",
    )
    parser.add_argument("action")

    args = parser.parse_args()

    action = args.action

    target_triple = args.target_triple
    host_platform = args.host_platform
    build_options = args.options
    python_source = (
        pathlib.Path(args.python_source) if args.python_source != "null" else None
    )
    dest_archive = pathlib.Path(args.dest_archive)
    docker_image = args.docker_image

    python_host_version = args.python_host_version

    settings = get_target_settings(TARGETS_CONFIG, target_triple)

    if args.action == "dockerfiles":
        log_name = "dockerfiles"
    elif args.action == "makefiles":
        log_name = "makefiles"
    elif args.action.startswith("image-"):
        log_name = "image-%s" % action
    elif args.toolchain:
        log_name = "%s-%s" % (action, host_platform)
    elif args.action.startswith("cpython-") and args.action.endswith("-host"):
        log_name = args.action
    else:
        entry = DOWNLOADS[action]
        log_name = "%s-%s-%s-%s" % (
            action,
            entry["version"],
            target_triple,
            build_options,
        )

    log_path = BUILD / "logs" / ("build.%s.log" % log_name)

    with log_path.open("wb") as log_fh:
        set_logger(action, log_fh)
        if action == "dockerfiles":
            write_dockerfiles(SUPPORT, BUILD)
        elif action == "makefiles":
            targets = get_targets(TARGETS_CONFIG)
            write_triples_makefiles(targets, BUILD, SUPPORT)
            write_target_settings(targets, BUILD / "targets")
            write_package_versions(BUILD / "versions")

            # Override the DOWNLOADS package entry for CPython for the local build
            if python_source:
                write_cpython_version(
                    BUILD / "versions", os.environ["PYBUILD_PYTHON_VERSION"]
                )

        elif action.startswith("image-"):
            image_name = action[6:]
            image_path = BUILD / ("%s.Dockerfile" % image_name)
            with image_path.open("rb") as fh:
                image_data = fh.read()

            build_docker_image(client, image_data, BUILD, image_name)

        elif action == "binutils":
            build_binutils(client, get_image(client, ROOT, BUILD, "gcc"), host_platform)

        elif action == "clang":
            materialize_clang(host_platform, target_triple)

        elif action == "musl":
            build_musl(
                client,
                get_image(client, ROOT, BUILD, "gcc"),
                host_platform,
                target_triple,
                build_options,
            )

        elif action == "autoconf":
            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                tools_path="host",
                extra_archives=["m4"],
            )

        elif action == "libedit":
            build_libedit(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
            )

        elif action in (
            "bdb",
            "bzip2",
            "expat",
            "libffi-3.3",
            "libffi",
            "libpthread-stubs",
            "m4",
            "mpdecimal",
            "ncurses",
            "openssl-1.1",
            "openssl-3.0",
            "patchelf",
            "sqlite",
            "tcl",
            "uuid",
            "x11-util-macros",
            "xorgproto",
            "xtrans",
            "xz",
            "zlib",
        ):
            tools_path = "host" if action in ("m4", "patchelf") else "deps"

            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                tools_path=tools_path,
            )

        elif action == "libX11":
            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                extra_archives={
                    "libpthread-stubs",
                    "libXau",
                    "libxcb",
                    "x11-util-macros",
                    "xorgproto",
                    "xtrans",
                },
            )

        elif action == "libXau":
            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                extra_archives={"x11-util-macros", "xorgproto"},
            )

        elif action == "xcb-proto":
            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                python_host_version=python_host_version,
            )

        elif action == "libxcb":
            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                extra_archives={"libpthread-stubs", "libXau", "xcb-proto", "xorgproto"},
                python_host_version=python_host_version,
            )

        elif action == "tix":
            build_tix(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
            )

        elif action == "tk":
            extra_archives = {"tcl"}
            if not host_platform.startswith("macos_"):
                extra_archives |= {
                    "libX11",
                    "libXau",
                    "libxcb",
                    "xcb-proto",
                    "xorgproto",
                }

            simple_build(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                extra_archives=extra_archives,
                python_host_version=python_host_version,
            )

        elif action.startswith("cpython-") and action.endswith("-host"):
            build_cpython_host(
                client,
                get_image(client, ROOT, BUILD, docker_image),
                action[:-5],
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
            )

        elif action in (
            "cpython-3.9",
            "cpython-3.10",
            "cpython-3.11",
            "cpython-3.12",
            "cpython-3.13",
            "cpython-3.14",
        ):
            build_cpython(
                settings,
                client,
                get_image(client, ROOT, BUILD, docker_image),
                host_platform=host_platform,
                target_triple=target_triple,
                build_options=build_options,
                dest_archive=dest_archive,
                version=action.split("-")[1],
                python_source=python_source,
            )

        else:
            print("unknown build action: %s" % action)
            return 1


if __name__ == "__main__":
    sys.exit(main())
