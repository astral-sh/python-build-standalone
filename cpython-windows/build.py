#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import concurrent.futures
import hashlib
import io
import json
import multiprocessing
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from pythonbuild.cpython import (
    STDLIB_TEST_PACKAGES,
    meets_python_maximum_version,
    meets_python_minimum_version,
    parse_config_c,
    stdlib_test_annotations,
)
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.utils import (
    compress_python_archive,
    create_tar_from_directory,
    default_target_triple,
    download_entry,
    extract_tar_to_directory,
    extract_zip_to_directory,
    hash_path,
    normalize_tar_archive,
    release_tag_from_git,
    validate_python_json,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
SUPPORT = ROOT / "cpython-windows"
STDLIB_TEST_ANNOTATIONS = ROOT / "stdlib-test-annotations.yml"
OPENSSL_ENTRY = "openssl-3.5"
LIBFFI_REVISION = "16fad4855b3d8c03b5910e405ff3a04395b39a98"

TARGET_ARCHITECTURES = {
    "i686-pc-windows-msvc": "x86",
    "x86_64-pc-windows-msvc": "amd64",
    "aarch64-pc-windows-msvc": "arm64",
}

LOG_PREFIX = [None]
LOG_FH = [None]

# Extensions that need to be converted from standalone to built-in.
# Key is name of VS project representing the standalone extension.
# Value is dict describing the extension.
CONVERT_TO_BUILTIN_EXTENSIONS = {
    "_asyncio": {
        # _asynciomodule.c is included in pythoncore for some reason.
        # This was fixed in Python 3.9. See hacky code for
        # `honor_allow_missing_preprocessor`.
        "allow_missing_preprocessor": True
    },
    "_bz2": {},
    "_ctypes": {
        "shared_depends": ["libffi-8"],
    },
    "_decimal": {},
    "_elementtree": {},
    "_hashlib": {
        "shared_depends_amd64": ["libcrypto-1_1-x64"],
        "shared_depends_win32": ["libcrypto-1_1"],
    },
    "_lzma": {
        "ignore_additional_depends": {"$(OutDir)liblzma$(PyDebugExt).lib"},
    },
    "_msi": {
        # Removed in 3.13.
        "ignore_missing": True,
    },
    "_overlapped": {},
    "_multiprocessing": {},
    "_remote_debugging": {
        # Added in 3.14
        "ignore_missing": True
    },
    "_socket": {},
    "_sqlite3": {"shared_depends": ["sqlite3"]},
    # See the one-off calls to copy_link_to_lib() and elsewhere to hack up
    # project files.
    "_ssl": {
        "shared_depends_amd64": ["libcrypto-1_1-x64", "libssl-1_1-x64"],
        "shared_depends_win32": ["libcrypto-1_1", "libssl-1_1"],
    },
    "_tkinter": {
        "ignore_additional_depends": {"$(tcltkLib)"},
    },
    "_queue": {},
    "_uuid": {"ignore_missing": True},
    "_wmi": {
        # Introduced in 3.12.
        "ignore_missing": True,
    },
    "_zoneinfo": {"ignore_missing": True},
    "_zstd": {
        # Added in 3.14
        "ignore_missing": True
    },
    "pyexpat": {},
    "select": {},
    "unicodedata": {},
    "winsound": {},
}

REQUIRED_EXTENSIONS = {
    "_codecs",
    "_io",
    "_signal",
    "_thread",
    "_tracemalloc",
    "_weakref",
    "faulthandler",
}

# Used to annotate licenses.
EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY = {
    "_bz2": ["bzip2"],
    "_ctypes": ["libffi"],
    "_hashlib": ["openssl"],
    "_lzma": ["xz"],
    "_sqlite3": ["sqlite"],
    "_ssl": ["openssl"],
    "_tkinter": ["tcltk", "tix"],
    "_uuid": ["uuid"],
    "zlib": ["zlib"],
    "_zstd": ["zstd"],
}

# Tests to run during PGO profiling.
#
# This set was copied from test.libregrtest.pgo in the CPython source
# distribution.
PGO_TESTS = {
    "test_array",
    "test_base64",
    "test_binascii",
    "test_binop",
    "test_bisect",
    "test_bytes",
    "test_bz2",
    "test_cmath",
    "test_codecs",
    "test_collections",
    "test_complex",
    "test_dataclasses",
    "test_datetime",
    "test_decimal",
    "test_difflib",
    "test_embed",
    "test_float",
    "test_fstring",
    "test_functools",
    "test_generators",
    "test_hashlib",
    "test_heapq",
    "test_int",
    "test_itertools",
    "test_json",
    "test_long",
    "test_lzma",
    "test_math",
    "test_memoryview",
    "test_operator",
    "test_ordered_dict",
    "test_pickle",
    "test_pprint",
    "test_re",
    "test_set",
    # Renamed to test_sqlite3 in 3.11. We keep both names as we just look for
    # test presence in this set.
    "test_sqlite",
    "test_sqlite3",
    "test_statistics",
    "test_struct",
    "test_tabnanny",
    "test_time",
    "test_unicode",
    "test_xml_etree",
    "test_xml_etree_c",
}


def log(msg):
    if isinstance(msg, bytes):
        msg_str = msg.decode("utf-8", "replace")
        msg_bytes = msg
    else:
        msg_str = msg
        msg_bytes = msg.encode("utf-8", "replace")

    print(f"{LOG_PREFIX[0]}> {msg_str}")

    if LOG_FH[0]:
        LOG_FH[0].write(msg_bytes + b"\n")
        LOG_FH[0].flush()


def exec_and_log(args, cwd, env, exit_on_error=True):
    log(f"executing {' '.join(args)}")

    p = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    for line in iter(p.stdout.readline, b""):
        log(line.rstrip())

    p.wait()

    log(f"process exited {p.returncode}")

    if p.returncode and exit_on_error:
        sys.exit(p.returncode)


def find_vswhere():
    vswhere = (
        pathlib.Path(os.environ["ProgramFiles(x86)"])
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )

    if not vswhere.exists():
        print(f"{vswhere} does not exist")
        sys.exit(1)

    return vswhere


def find_vs_path(path, msvc_version):
    vswhere = find_vswhere()

    if msvc_version == "2019":
        version = "[16,17)"
    elif msvc_version == "2022":
        version = "[17,18)"
    elif msvc_version == "2026":
        version = "[18,19)"
    else:
        raise ValueError(f"unsupported Visual Studio version: {msvc_version}")

    p = subprocess.check_output(
        [
            str(vswhere),
            "-utf8",
            "-latest",
            "-version",
            version,
            "-property",
            "installationPath",
            "-products",
            "*",
        ]
    )

    p = pathlib.Path(p.strip().decode("utf-8"))

    p = p / path

    if not p.exists():
        print(f"{p} does not exist")
        sys.exit(1)

    return p


def find_vcvarsall_path(msvc_version):
    """Find path to vcvarsall.bat"""
    return find_vs_path(
        pathlib.Path("VC") / "Auxiliary" / "Build" / "vcvarsall.bat", msvc_version
    )


def get_visual_studio_environment(
    msvc_version: str, arch: str, vc_tools_version: str
) -> dict[str, str]:
    """Return the selected Visual Studio build environment."""
    vcvarsall = find_vcvarsall_path(msvc_version)
    log(
        f"activating Visual Studio {msvc_version}: {vcvarsall} {arch} "
        f"-vcvars_ver={vc_tools_version}"
    )

    marker = "__PYBUILD_VCVARS_ENV__"
    # Use a command string so cmd.exe receives the batch path's quotes intact.
    # /u makes the environment dump UTF-16, preserving non-ASCII paths.
    command = (
        f'cmd.exe /d /u /s /c "call "{vcvarsall}" {arch}'
        f' -vcvars_ver={vc_tools_version} && echo {marker} && set"'
    )
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-16le",
    )
    output, separator, environment = result.stdout.partition(marker)
    log(output.rstrip())
    result.check_returncode()
    if not separator:
        raise RuntimeError("Visual Studio setup did not return a build environment")

    env = {}
    for line in environment.splitlines():
        name, separator, value = line.partition("=")
        # cmd.exe can include internal drive-directory entries such as =C:.
        if name and separator:
            env[name] = value

    return env


class NoSearchStringError(Exception):
    """Represents a missing search string when replacing content in a file."""


def static_replace_in_file(p: pathlib.Path, search, replace):
    """Replace occurrences of a string in a file.

    The updated file contents are written out in place.
    """

    with p.open("rb") as fh:
        data = fh.read()

    # Build should be as deterministic as possible. Assert that wanted changes
    # actually occur.
    if search not in data:
        raise NoSearchStringError(f"search string ({search}) not in {p}")

    log(f"replacing `{search}` with `{replace}` in {p}")
    data = data.replace(search, replace)

    with p.open("wb") as fh:
        fh.write(data)


def apply_source_patch(source_path: pathlib.Path, patch_path: pathlib.Path):
    log(f"applying {patch_path.name} to {source_path}")
    with patch_path.open("rb") as fh:
        patch = fh.read().replace(b"\r\n", b"\n")

    # Release archives contain CRLF project files. Normalize them for matching
    # LF patches and write CRLF output without ignoring whitespace differences.
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "-C",
            str(source_path),
            "apply",
            "--whitespace=nowarn",
            "-",
        ],
        input=patch,
        check=True,
    )


def apply_cpython_patches(cpython_source_path: pathlib.Path, python_version: str):
    # Omit UWP executables, the legacy launcher, and the shell extension to
    # reduce build time and keep them out of the distribution artifacts.
    patches = ["patch-disable-uwp.patch"]

    # The legacy launcher and shell extension are present through Python 3.15.
    # https://github.com/python/cpython/pull/153512
    if meets_python_maximum_version(python_version, "3.15"):
        patches.append("patch-disable-launchers.patch")

    # Keep the SQLite features in sync with `cpython-unix/build-sqlite.sh`.
    if meets_python_minimum_version(python_version, "3.15"):
        patches.append("patch-sqlite-build-flags-3.15.patch")
    else:
        patches.append("patch-sqlite-build-flags.patch")

    # Our xz sources need the project changes included in Python 3.15 for xz 5.8.1.
    # https://github.com/python/cpython/pull/141022
    if meets_python_maximum_version(python_version, "3.13"):
        patches.append("patch-liblzma-5.8.patch")
    elif meets_python_maximum_version(python_version, "3.14"):
        patches.append("patch-liblzma-5.8-3.14.patch")

    # Older layout scripts disable Tcl/Tk on ARM64.
    # https://github.com/python/cpython/pull/132650
    if meets_python_maximum_version(python_version, "3.12"):
        patches.append("patch-layout-tcltk-arm64.patch")

    if meets_python_maximum_version(python_version, "3.11"):
        # Our OpenSSL build installs `applink.c` under `include/openssl`, while
        # these CPython projects expect it directly under `include`.
        patches.append("patch-openssl-applink.patch")
        # The Tcl/Tk bundle also needs its zlib DLL copied into the build.
        patches.append("patch-tkinter-zlib.patch")

    for patch in patches:
        apply_source_patch(cpython_source_path, SUPPORT / patch)


OPENSSL_PROPS_REMOVE_RULES = rb"""
  <ItemGroup>
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).pdb" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).pdb" />
  </ItemGroup>
  <Target Name="_CopySSLDLL"
          Inputs="@(_SSLDLL)"
          Outputs="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')"
          Condition="$(SkipCopySSLDLL) == ''"
          AfterTargets="Build">
    <Copy SourceFiles="@(_SSLDLL)" DestinationFolder="$(OutDir)" />
  </Target>
  <Target Name="_CleanSSLDLL" Condition="$(SkipCopySSLDLL) == ''" BeforeTargets="Clean">
    <Delete Files="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')" TreatErrorsAsWarnings="true" />
  </Target>
"""

LIBFFI_PROPS_REMOVE_RULES = b"""
  <Target Name="_CopyLIBFFIDLL" Inputs="@(_LIBFFIDLL)" Outputs="@(_LIBFFIDLL->'$(OutDir)%(Filename)%(Extension)')" AfterTargets="Build">
    <Copy SourceFiles="@(_LIBFFIDLL)" DestinationFolder="$(OutDir)" />
  </Target>
"""


def hack_openssl_props(pcbuild_path: pathlib.Path, arch: str):
    # We want to statically link against OpenSSL. This requires using our own
    # OpenSSL build. This requires some hacking of various files.
    openssl_props = pcbuild_path / "openssl.props"

    if arch == "amd64":
        suffix = b"-x64"
    elif arch == "win32":
        suffix = b""
    elif arch == "arm64":
        suffix = b""
    else:
        raise Exception(f"unhandled architecture: {arch}")

    static_replace_in_file(
        openssl_props,
        b"<_DLLSuffix>-3</_DLLSuffix>",
        b"<_DLLSuffix>-3%s</_DLLSuffix>" % suffix,
    )


def hack_project_files(
    cpython_source_path: pathlib.Path,
    build_directory: str,
    python_version: str,
):
    """Hacks Visual Studio project files to work with our build."""

    pcbuild_path = cpython_source_path / "PCbuild"

    apply_cpython_patches(cpython_source_path, python_version)
    hack_openssl_props(pcbuild_path, build_directory)

    # Our SQLite directory is named weirdly. This throws off version detection
    # in the project file. Replace the parsing logic with a static string.
    sqlite3_version = DOWNLOADS["sqlite"]["actual_version"].encode("ascii")
    sqlite3_version_parts = sqlite3_version.split(b".")
    sqlite3_path = pcbuild_path / "sqlite3.vcxproj"
    static_replace_in_file(
        sqlite3_path,
        rb"<_SqliteVersion>$([System.Text.RegularExpressions.Regex]::Match(`$(sqlite3Dir)`, `((\d+)\.(\d+)\.(\d+)\.(\d+))\\?$`).Groups)</_SqliteVersion>",
        rb"<_SqliteVersion>%s</_SqliteVersion>" % sqlite3_version,
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteVersion>$(_SqliteVersion.Split(`;`)[1])</SqliteVersion>",
        rb"<SqliteVersion>%s</SqliteVersion>" % sqlite3_version,
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMajorVersion>$(_SqliteVersion.Split(`;`)[2])</SqliteMajorVersion>",
        rb"<SqliteMajorVersion>%s</SqliteMajorVersion>" % sqlite3_version_parts[0],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMinorVersion>$(_SqliteVersion.Split(`;`)[3])</SqliteMinorVersion>",
        rb"<SqliteMinorVersion>%s</SqliteMinorVersion>" % sqlite3_version_parts[1],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMicroVersion>$(_SqliteVersion.Split(`;`)[4])</SqliteMicroVersion>",
        rb"<SqliteMicroVersion>%s</SqliteMicroVersion>" % sqlite3_version_parts[2],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqlitePatchVersion>$(_SqliteVersion.Split(`;`)[5])</SqlitePatchVersion>",
        rb"<SqlitePatchVersion>%s</SqlitePatchVersion>" % sqlite3_version_parts[3],
    )


def run_msbuild(
    msbuild: pathlib.Path,
    pcbuild_path: pathlib.Path,
    dependency_paths: dict[str, pathlib.Path],
    configuration: str,
    platform: str,
    python_version: str,
    windows_sdk_version: str,
    platform_toolset: str,
    freethreaded: bool,
):
    args = [
        str(msbuild),
        str(pcbuild_path / "pcbuild.proj"),
        "/target:Build",
        f"/property:Configuration={configuration}",
        f"/property:Platform={platform}",
        f"/property:PlatformToolset={platform_toolset}",
        "/maxcpucount",
        "/nologo",
        "/verbosity:normal",
        "/property:IncludeExternals=true",
        "/property:IncludeSSL=true",
        "/property:IncludeTkinter=true",
        "/property:IncludeTests=true",
        f"/property:OverrideVersion={python_version}",
        "/property:IncludeCTypes=true",
        # We pin the Windows 10 SDK version to make builds more deterministic.
        # This can also work around known incompatibilities with the Windows 11
        # SDK as of at least CPython 3.9.7.
        f"/property:DefaultWindowsSDKVersion={windows_sdk_version}",
    ]

    # CPython expects directory properties to end in a separator, except for
    # opensslIncludeDir, where project files add it themselves.
    for name, path in dependency_paths.items():
        value = str(path)
        if name != "opensslIncludeDir":
            value += "\\"
        args.append(f"/property:{name}={value}")

    if freethreaded:
        args.append("/property:DisableGil=true")

    # Build tail-calling Python for 3.15+, but not in Debug. [[msvc::musttail]]
    # requires /O2 and under /Od MSVC reports C4737 at every dispatch site.
    # See https://learn.microsoft.com/en-us/cpp/cpp/attributes#msvcmusttail
    # and https://github.com/python/cpython/issues/148047
    if (
        meets_python_minimum_version(python_version, "3.15")
        and platform == "x64"
        and configuration != "Debug"
    ):
        args.append("/property:UseTailCallInterp=true")

    exec_and_log(args, str(pcbuild_path), os.environ)


def build_openssl_for_arch(
    perl_path,
    arch: str,
    openssl_archive,
    openssl_version: str,
    nasm_archive,
    build_root: pathlib.Path,
    *,
    jom_archive,
    with_uplink: bool = False,
):
    nasm_version = DOWNLOADS["nasm-windows-bin"]["version"]

    log(f"extracting {openssl_archive} to {build_root}")
    extract_tar_to_directory(openssl_archive, build_root)
    log(f"extracting {nasm_archive} to {build_root}")
    extract_zip_to_directory(nasm_archive, build_root)
    log(f"extracting {jom_archive} to {build_root}")
    extract_zip_to_directory(jom_archive, build_root / "jom")

    nasm_path = build_root / f"nasm-{nasm_version}"
    jom_path = build_root / "jom"

    env = dict(os.environ)
    # Add Perl and nasm paths to front of PATH.
    env["PATH"] = f"{perl_path.parent};{nasm_path};{jom_path};{env['PATH']}"

    source_root = build_root / f"openssl-{openssl_version}"

    if with_uplink:
        # uplink.c tries to find the OPENSSL_Applink function exported from the
        # current executable. However, it is exported from _ssl[_d].pyd in shared
        # builds. So update its source to look for it from there.
        apply_source_patch(source_root, SUPPORT / "patch-openssl-uplink.patch")

    if arch == "x86":
        configure = "VC-WIN32"
        prefix = "32"
    elif arch == "amd64":
        configure = "VC-WIN64A"
        prefix = "64"
    elif arch == "arm64":
        configure = "VC-WIN64-ARM"
        prefix = "arm64"
    else:
        raise Exception(f"unhandled architecture: {arch}")

    # Set DESTDIR to affect install location.
    dest_dir = build_root / "install"
    env["DESTDIR"] = str(dest_dir)
    install_root = dest_dir / prefix

    configure_args = [
        str(perl_path),
        "Configure",
        configure,
        "no-idea",
        "no-mdc2",
        "no-tests",
        f"--prefix=/{prefix}",
    ]
    if with_uplink:
        log("building OpenSSL with uplink support for Python <3.12")
    else:
        configure_args.append("no-uplink")

    exec_and_log(
        configure_args,
        source_root,
        {
            **env,
            "CFLAGS": env.get("CFLAGS", "") + " /FS",
        },
    )

    # exec_and_log(["nmake"], source_root, env)
    exec_and_log(
        [str(jom_path / "jom"), "/J", str(multiprocessing.cpu_count())],
        source_root,
        env,
    )

    # We don't care about accessory files, docs, etc. So just run `install_sw`
    # target to get the main files.
    exec_and_log(["nmake", "install_sw"], source_root, env)

    # Copy the _static libraries as well.
    for l in ("crypto", "ssl"):
        basename = f"lib{l}_static.lib"
        source = source_root / basename
        dest = install_root / "lib" / basename
        log(f"copying {source} to {dest}")
        shutil.copyfile(source, dest)

    # Copy `applink.c` to the include directory.
    source_applink = source_root / "ms" / "applink.c"
    dest_applink = install_root / "include" / "openssl" / "applink.c"
    log(f"copying {source_applink} to {dest_applink}")
    shutil.copyfile(source_applink, dest_applink)


def build_openssl(
    entry: str,
    perl_path: pathlib.Path,
    arch: str,
    dest_archive: pathlib.Path,
    with_uplink: bool = False,
):
    """Build OpenSSL from sources using the Perl executable specified."""

    openssl_version = DOWNLOADS[entry]["version"]

    # First ensure the dependencies are in place.
    openssl_archive = download_entry(entry, BUILD)
    nasm_archive = download_entry("nasm-windows-bin", BUILD)
    jom_archive = download_entry("jom-windows-bin", BUILD)

    with tempfile.TemporaryDirectory(prefix="openssl-build-") as td:
        td = pathlib.Path(td)

        root_32 = td / "x86"
        root_64 = td / "x64"
        root_arm64 = td / "arm64"

        if arch == "x86":
            root_32.mkdir()
            build_openssl_for_arch(
                perl_path,
                "x86",
                openssl_archive,
                openssl_version,
                nasm_archive,
                root_32,
                jom_archive=jom_archive,
                with_uplink=with_uplink,
            )
        elif arch == "amd64":
            root_64.mkdir()
            build_openssl_for_arch(
                perl_path,
                "amd64",
                openssl_archive,
                openssl_version,
                nasm_archive,
                root_64,
                jom_archive=jom_archive,
                with_uplink=with_uplink,
            )
        elif arch == "arm64":
            root_arm64.mkdir()
            build_openssl_for_arch(
                perl_path,
                "arm64",
                openssl_archive,
                openssl_version,
                nasm_archive,
                root_arm64,
                jom_archive=jom_archive,
                with_uplink=with_uplink,
            )
        else:
            raise Exception(f"unhandled architecture: {arch}")

        install = td / "out"

        if arch == "x86":
            shutil.copytree(root_32 / "install" / "32", install / "openssl" / "win32")
        elif arch == "arm64":
            shutil.copytree(
                root_arm64 / "install" / "arm64", install / "openssl" / "arm64"
            )
        else:
            shutil.copytree(root_64 / "install" / "64", install / "openssl" / "amd64")

        with dest_archive.open("wb") as fh:
            create_tar_from_directory(fh, install)


def build_libffi(
    python: str,
    arch: str,
    sh_exe: pathlib.Path,
    msvc_version: str,
    vc_tools_version: str,
    dest_archive: pathlib.Path,
):
    with tempfile.TemporaryDirectory(prefix="libffi-build-") as td:
        td = pathlib.Path(td)

        ffi_source_path = td / "libffi"

        # As of April 15, 2020, the libffi source release on GitHub doesn't
        # have patches that we need to build. https://bugs.python.org/issue40293
        # tracks getting a proper release. Until then, git clone the repo.
        subprocess.run(
            [
                "git.exe",
                "-c",
                "core.autocrlf=input",
                "clone",
                "--single-branch",
                "--branch",
                "libffi",
                "https://github.com/python/cpython-source-deps.git",
                str(ffi_source_path),
            ],
            check=True,
        )

        subprocess.run(
            [
                "git.exe",
                "-c",
                "core.autocrlf=input",
                "checkout",
                LIBFFI_REVISION,
            ],
            cwd=ffi_source_path,
            check=True,
        )

        # We build libffi by running the build script that CPython ships.
        python_archive = download_entry(python, BUILD)
        extract_tar_to_directory(python_archive, td)

        python_entry = DOWNLOADS[python]
        prepare_libffi = (
            td / f"Python-{python_entry['version']}" / "PCbuild" / "prepare_libffi.bat"
        )
        # The upstream script activates Visual Studio again. Keep it on the
        # same version selection as OpenSSL and CPython, and stop if setup fails.
        static_replace_in_file(
            prepare_libffi,
            b"call %VCVARSALL% %VCVARS_PLATFORM%",
            (
                f"call %VCVARSALL% %VCVARS_PLATFORM% -vcvars_ver={vc_tools_version}\n"
                "if errorlevel 1 exit /B %ERRORLEVEL%"
            ).encode("ascii"),
        )

        env = dict(os.environ)
        env["LIBFFI_SOURCE"] = str(ffi_source_path)
        env["VCVARSALL"] = str(find_vcvarsall_path(msvc_version))
        env["SH"] = str(sh_exe)

        args = [str(prepare_libffi), "-pdb"]
        if arch == "x86":
            args.append("-x86")
            artifacts_path = ffi_source_path / "i686-pc-cygwin"
        elif arch == "arm64":
            args.append("-arm64")
            artifacts_path = ffi_source_path / "aarch64-w64-cygwin"
        elif arch == "amd64":
            args.append("-x64")
            artifacts_path = ffi_source_path / "x86_64-w64-cygwin"
        else:
            raise Exception(f"unhandled architecture: {arch}")

        subprocess.run(args, env=env, check=True)

        out_dir = td / "out" / "libffi"
        out_dir.mkdir(parents=True)

        for f in os.listdir(artifacts_path / ".libs"):
            if f.endswith((".lib", ".exp", ".dll", ".pdb")):
                shutil.copyfile(artifacts_path / ".libs" / f, out_dir / f)

        shutil.copytree(artifacts_path / "include", out_dir / "include")
        shutil.copyfile(
            artifacts_path / "fficonfig.h", out_dir / "include" / "fficonfig.h"
        )

        with dest_archive.open("wb") as fh:
            create_tar_from_directory(fh, td / "out")


RE_ADDITIONAL_DEPENDENCIES = re.compile(
    "<AdditionalDependencies>([^<]+)</AdditionalDependencies>"
)


def collect_python_build_artifacts(
    pcbuild_path: pathlib.Path,
    out_dir: pathlib.Path,
    python_majmin: str,
    pcbuild_directory: str,
    config: str,
    openssl_entry: str,
    zlib_entry: str,
    freethreaded: bool,
    tk_bin_entry: str,
    tcltk_dlls: list[str],
):
    """Collect build artifacts from Python.
    Copies them into an output directory and returns a data structure describing
    the files.
    """
    arch = pcbuild_directory
    # Python 3.15 suffixes the directory with 't' for free-threading
    if arch.endswith("t"):
        arch = arch.removesuffix("t")
    outputs_path = pcbuild_path / pcbuild_directory
    intermediates_path = (
        pcbuild_path / "obj" / f"{python_majmin}{pcbuild_directory}_{config}"
    )

    if not outputs_path.exists():
        log(f"{outputs_path} does not exist")
        sys.exit(1)

    if not intermediates_path.exists():
        log(f"{intermediates_path} does not exist")
        sys.exit(1)

    # Things we want to collect:
    # 1. object files that contribute to libpython
    # 2. libraries for dependencies

    # The build throws everything in the same directory hierarchy, so we can't
    # easily filter by path to identify e.g. core versus extensions. We rely on
    # tagging projects instead. We validate that all directories are known to
    # us.

    # Projects that aren't relevant to us.
    ignore_projects = {
        # We don't care about build artifacts for the python executable.
        "python",
        "pythonw",
        # Used to bootstrap interpreter.
        "_freeze_module",
        # Don't care about venvlauncher executable.
        "venvlauncher",
        "venvwlauncher",
        # Test extensions.
        "_ctypes_test",
        "_testbuffer",
        "_testcapi",
        "_testclinic_limited",
        "_testclinic",
        "_testconsole",
        "_testembed",
        "_testimportmultiple",
        "_testinternalcapi",
        "_testlimitedcapi",
        "_testmultiphase",
        "_testsinglephase",
        "xxlimited_35",
        "xxlimited",
    }

    other_projects = {"pythoncore"}
    other_projects.add("python3dll")
    other_projects.add("python3tdll")

    # Projects providing dependencies.
    depends_projects = set()

    # Projects that provide extensions.
    extension_projects = set()

    dirs = {p for p in os.listdir(intermediates_path)}

    for extension, entry in CONVERT_TO_BUILTIN_EXTENSIONS.items():
        if extension not in dirs:
            if entry.get("ignore_missing"):
                continue
            else:
                log(f"extension not present: {extension}")
                sys.exit(1)

        extension_projects.add(extension)

    depends_projects |= {
        "liblzma",
        "sqlite3",
    }

    if zlib_entry == "zlib-ng":
        depends_projects |= {"zlib-ng"}

    known_projects = (
        ignore_projects | other_projects | depends_projects | extension_projects
    )

    unknown = dirs - known_projects

    if unknown:
        names = ", ".join(sorted(unknown))
        log(f"encountered build directory for unknown projects: {names}")
        sys.exit(1)

    res = {"core": {"objs": []}, "extensions": {}}

    res["object_file_format"] = "coff"

    def process_project(project: pathlib.Path, dest_dir: pathlib.Path):
        for f in sorted(os.listdir(intermediates_path / project)):
            p = intermediates_path / project / f
            dest = dest_dir / p.name

            if p.suffix == ".obj":
                log(f"copying object file {p} to {dest_dir}")
                shutil.copyfile(p, dest)
                yield f

    def find_additional_dependencies(project: pathlib.Path):
        vcproj = pcbuild_path / f"{project}.vcxproj"

        with vcproj.open("r", encoding="utf8") as fh:
            for line in fh:
                m = RE_ADDITIONAL_DEPENDENCIES.search(line)

                if not m:
                    continue

                depends = set(m.group(1).split(";"))
                depends.discard("%(AdditionalDependencies)")

                return depends

        return set()

    if arch == "amd64":
        abi_platform = "win_amd64"
    elif arch == "win32":
        abi_platform = "win32"
    elif arch == "arm64":
        abi_platform = "win_arm64"
    else:
        raise Exception(f"unhandled architecture: {arch}")

    debug_suffix = "_d" if config == "Debug" else ""
    if freethreaded:
        abi_tag = f"{debug_suffix}.cp{python_majmin}t-{abi_platform}"
        lib_suffix = f"t{debug_suffix}"
    else:
        abi_tag = debug_suffix
        lib_suffix = debug_suffix

    # Copy object files for core sources into their own directory.
    core_dir = out_dir / "build" / "core"
    core_dir.mkdir(parents=True)

    for obj in process_project("pythoncore", core_dir):
        res["core"]["objs"].append(f"build/core/{obj}")

    # Copy config.c into output directory, next to its object file.
    shutil.copyfile(
        pcbuild_path / ".." / "PC" / "config.c", out_dir / "build" / "core" / "config.c"
    )

    assert "build/core/config.obj" in res["core"]["objs"]
    res["inittab_object"] = "build/core/config.obj"
    res["inittab_source"] = "build/core/config.c"
    res["inittab_cflags"] = ["-DNDEBUG", "-DPy_BUILD_CORE"]

    exts = ("lib", "exp")

    for ext in exts:
        source = outputs_path / f"python{python_majmin}{lib_suffix}.{ext}"
        dest = core_dir / f"python{python_majmin}{lib_suffix}.{ext}"
        log(f"copying {source}")
        shutil.copyfile(source, dest)

    res["core"]["shared_lib"] = f"install/python{python_majmin}{lib_suffix}.dll"

    # We hack up pythoncore.vcxproj and the list in it when this function
    # runs isn't totally accurate. We hardcode the list from the CPython
    # distribution.
    # TODO pull from unaltered file
    res["core"]["links"] = [
        {"name": "version", "system": True},
        {"name": "ws2_32", "system": True},
        # In addition to the ones explicitly in the project, there are some
        # implicit link libraries not present. We list those as well.
        {"name": "Ole32", "system": True},
        {"name": "OleAut32", "system": True},
        {"name": "User32", "system": True},
        # Presence of pathcch drops support for Windows 7.
        {"name": "pathcch", "system": True},
    ]

    # Copy files for extensions into their own directories.
    for ext in sorted(extension_projects):
        dest_dir = out_dir / "build" / "extensions" / ext
        dest_dir.mkdir(parents=True)

        additional_depends = find_additional_dependencies(ext)
        additional_depends -= CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get(
            "ignore_additional_depends", set()
        )

        entry = {
            "in_core": False,
            "objs": [],
            "init_fn": f"PyInit_{ext}",
            "shared_lib": None,
            "static_lib": None,
            "links": [
                {"name": n[:-4], "system": True} for n in sorted(additional_depends)
            ],
            "variant": "default",
        }

        if ext == "_tkinter":
            entry["links"].extend(
                {"name": name, "path_dynamic": f"install/DLLs/{name}.dll"}
                for name in tcltk_dlls
            )

        for obj in process_project(ext, dest_dir):
            entry["objs"].append(f"build/extensions/{ext}/{obj}")

        for lib in CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get("shared_depends", []):
            entry["links"].append(
                {"name": lib, "path_dynamic": f"install/DLLs/{lib}.dll"}
            )

        for lib in CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get(
            f"shared_depends_{arch}", []
        ):
            entry["links"].append(
                {"name": lib, "path_dynamic": f"install/DLLs/{lib}.dll"}
            )

        if ext in EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY:
            licenses = set()
            license_paths = set()
            license_public_domain = False

            for name in EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY[ext]:
                if name == "openssl":
                    name = openssl_entry

                if name == "zlib":
                    name = zlib_entry

                if name == "tcltk":
                    name = tk_bin_entry

                # Tix is only included in the Tcl/Tk 8.6 bundle.
                if name == "tix" and int(python_majmin) >= 314:
                    continue

                download_entry = DOWNLOADS[name]

                # This will raise if no license metadata defined. This is
                # intentional because EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY is
                # manually curated and we want to fail fast.
                licenses |= set(download_entry["licenses"])
                license_paths.add(f"licenses/{download_entry['license_file']}")
                license_public_domain = download_entry.get("license_public_domain")

            entry["licenses"] = list(sorted(licenses))
            entry["license_paths"] = list(sorted(license_paths))
            entry["license_public_domain"] = license_public_domain

        res["extensions"][ext] = [entry]

        # Copy the extension static library.
        ext_static = outputs_path / f"{ext}{abi_tag}.lib"
        dest = dest_dir / f"{ext}{abi_tag}.lib"
        log(f"copying static extension {ext_static}")
        shutil.copyfile(ext_static, dest)

        res["extensions"][ext][0]["shared_lib"] = f"install/DLLs/{ext}{abi_tag}.pyd"

    lib_dir = out_dir / "build" / "lib"
    lib_dir.mkdir()

    # Copy libraries for dependencies into the lib directory.
    for depend in sorted(depends_projects):
        static_source = outputs_path / f"{depend}{debug_suffix}.lib"
        static_dest = lib_dir / f"{depend}{debug_suffix}.lib"

        log(f"copying link library {static_source}")
        shutil.copyfile(static_source, static_dest)

        shared_source = outputs_path / f"{depend}{debug_suffix}.dll"
        if shared_source.exists():
            shared_dest = lib_dir / f"{depend}{debug_suffix}.dll"
            log(f"copying shared library {shared_source}")
            shutil.copyfile(shared_source, shared_dest)

    return res


def install_tcltk(tcltk_dir: pathlib.Path, install_dir: pathlib.Path):
    """Install the selected bundle's runtime DLLs and Tcl package directories."""
    dlls = sorted((tcltk_dir / "bin").glob("*.dll"))
    if not dlls:
        raise FileNotFoundError(f"No Tcl/Tk DLLs found in {tcltk_dir}")

    dll_dir = install_dir / "DLLs"
    dll_dir.mkdir(parents=True, exist_ok=True)
    for source in dlls:
        log(f"copying {source} to {dll_dir}")
        shutil.copy2(source, dll_dir / source.name)

    library_paths = []
    for source in sorted((tcltk_dir / "lib").iterdir()):
        if source.is_dir() and source.name != "nmake":
            dest = install_dir / "tcl" / source.name
            log(f"copying {source} to {dest}")
            shutil.copytree(source, dest, dirs_exist_ok=True)
            library_paths.append(source.name)

    return [path.stem for path in dlls], library_paths


def build_cpython(
    python_entry_name: str,
    target_triple: str,
    arch: str,
    build_options: str,
    platform_toolset: str,
    windows_sdk_version: str,
    openssl_archive,
    libffi_archive,
    openssl_entry: str,
) -> pathlib.Path:
    parsed_build_options = set(build_options.split("+"))
    debug = "debug" in parsed_build_options
    pgo = "pgo" in parsed_build_options
    freethreaded = "freethreaded" in parsed_build_options

    msbuild_path = shutil.which("MSBuild.exe")
    if msbuild_path is None:
        raise FileNotFoundError("MSBuild.exe was not found on PATH")
    msbuild = pathlib.Path(msbuild_path)
    log(f"using MSBuild from PATH: {msbuild}")

    # The python.props file keys off MSBUILD, so it needs to be set.
    os.environ["MSBUILD"] = str(msbuild)

    python_archive = download_entry(python_entry_name, BUILD)
    entry = DOWNLOADS[python_entry_name]
    python_version = entry["version"]

    zlib_entry = (
        "zlib-ng" if meets_python_minimum_version(python_version, "3.14") else "zlib"
    )

    bzip2_archive = download_entry("bzip2", BUILD)
    sqlite_archive = download_entry("sqlite", BUILD)
    xz_archive = download_entry("xz", BUILD)
    zlib_archive = download_entry(zlib_entry, BUILD)

    setuptools_wheel = download_entry("setuptools", BUILD)
    pip_wheel = download_entry("pip", BUILD)

    # Use upstream CPython's prebuilt bundles, retaining Tcl/Tk 8.6 before 3.14.
    if meets_python_minimum_version(python_version, "3.14"):
        tk_bin_entry = "tk-windows-bin-904"
    else:
        tk_bin_entry = "tk-windows-bin-8615"
    tk_bin_archive = download_entry(
        tk_bin_entry, BUILD, local_name="tk-windows-bin.tar.gz"
    )

    # On CPython 3.14+, zstd is included
    if meets_python_minimum_version(python_version, "3.14"):
        zstd_archive = download_entry("zstd", BUILD)
    else:
        zstd_archive = None

    # CPython 3.13+ no longer uses a bundled `mpdecimal` version so we build it
    if meets_python_minimum_version(python_version, "3.13"):
        mpdecimal_archive = download_entry("mpdecimal", BUILD)
    else:
        # TODO: Consider using the built mpdecimal for earlier versions as well,
        # as we do for Unix builds.
        mpdecimal_archive = None

    debug_suffix = "_d" if debug else ""
    if freethreaded:
        (major, minor, _) = python_version.split(".")
        python_exe = f"python{major}.{minor}t{debug_suffix}.exe"
    else:
        python_exe = f"python{debug_suffix}.exe"

    # Python 3.15 uses the default name for the executable in a suffixed directory
    instrumented_python_exe = python_exe
    if meets_python_minimum_version(python_version, "3.15") and freethreaded:
        instrumented_python_exe = "python.exe"

    if arch == "amd64":
        build_platform = "x64"
        build_directory = "amd64"
    elif arch == "x86":
        build_platform = "win32"
        build_directory = "win32"
    elif arch == "arm64":
        build_platform = "arm64"
        build_directory = "arm64"
    else:
        raise Exception(f"unhandled architecture: {arch}")

    pcbuild_directory = build_directory
    # Starting with 3.15, free-threaded CPython outputs use a `t` suffix.
    # The third-party dependency archives still use the base architecture name.
    if freethreaded and meets_python_minimum_version(python_version, "3.15"):
        pcbuild_directory = f"{build_directory}t"

    test_annotations = stdlib_test_annotations(
        STDLIB_TEST_ANNOTATIONS,
        python_version,
        target_triple,
        parsed_build_options,
    )

    tempdir_opts = (
        {"ignore_cleanup_errors": True} if sys.version_info >= (3, 12) else {}
    )
    with tempfile.TemporaryDirectory(prefix="python-build-", **tempdir_opts) as td:
        td = pathlib.Path(td)

        with concurrent.futures.ThreadPoolExecutor(10) as e:
            fs = []
            for a in (
                python_archive,
                bzip2_archive,
                mpdecimal_archive,
                openssl_archive,
                sqlite_archive,
                tk_bin_archive,
                xz_archive,
                zlib_archive,
                zstd_archive,
            ):
                if a is None:
                    continue

                log(f"extracting {a} to {td}")
                fs.append(e.submit(extract_tar_to_directory, a, td))

            for f in fs:
                f.result()

        # Copy the config.h file used by upstream CPython for xz 5.8.1
        # https://github.com/python/cpython-source-deps/blob/665d407bd6bc941944db2152e4b5dca388ea586e/windows/config.h
        xz_version = DOWNLOADS["xz"]["version"]
        xz_path = td / f"xz-{xz_version}"
        config_src = SUPPORT / "xz-support" / "config.h"
        config_dest = xz_path / "windows" / "config.h"
        log(f"copying {config_src} to {config_dest}")
        shutil.copyfile(config_src, config_dest)

        extract_tar_to_directory(libffi_archive, td)

        # We need all the OpenSSL library files in the same directory to appease
        # install rules.
        openssl_arch = {"amd64": "amd64", "x86": "win32", "arm64": "arm64"}[arch]
        openssl_root = td / "openssl" / openssl_arch
        openssl_bin_path = openssl_root / "bin"
        openssl_lib_path = openssl_root / "lib"

        for f in sorted(os.listdir(openssl_bin_path)):
            if not f.startswith("lib"):
                continue

            source = openssl_bin_path / f
            dest = openssl_lib_path / f
            log(f"copying {source} to {dest}")
            shutil.copyfile(source, dest)

        bzip2_path = td / f"bzip2-{DOWNLOADS['bzip2']['version']}"
        tcltk_commit = DOWNLOADS[tk_bin_entry]["git_commit"]
        tcltk_path = td / f"cpython-bin-deps-{tcltk_commit}"
        zlib_prefix = "cpython-source-deps-" if zlib_entry == "zlib-ng" else ""
        zlib_path = td / f"{zlib_prefix}{zlib_entry}-{DOWNLOADS[zlib_entry]['version']}"
        dependency_paths = {
            "bz2Dir": bzip2_path,
            "tcltkDir": tcltk_path / build_directory,
            "sqlite3Dir": td / f"sqlite-autoconf-{DOWNLOADS['sqlite']['version']}",
            "libffiOutDir": td / "libffi",
            "lzmaDir": xz_path,
            "opensslIncludeDir": openssl_root / "include",
            "opensslOutDir": openssl_lib_path,
            "zlibDir": zlib_path,
        }
        if zlib_entry == "zlib-ng":
            dependency_paths["zlibNgDir"] = zlib_path
        if zstd_archive is not None:
            dependency_paths["zstdDir"] = (
                td / f"cpython-source-deps-zstd-{DOWNLOADS['zstd']['version']}"
            )
        if mpdecimal_archive is not None:
            dependency_paths["mpdecimalDir"] = (
                td / f"mpdecimal-{DOWNLOADS['mpdecimal']['version']}"
            )

        # Delete the tk nmake helper, it's not needed and links msvc
        (
            tcltk_path
            / build_directory
            / "lib"
            / "nmake"
            / "x86_64-w64-mingw32-nmakehlp.exe"
        ).unlink()

        cpython_source_path = td / f"Python-{python_version}"

        # Keep ensurepip's bundled pip in sync with the pip installed below.
        ensurepip = cpython_source_path / "Lib" / "ensurepip"
        bundled = ensurepip / "_bundled"
        for wheel in bundled.glob("pip-*.whl"):
            wheel.unlink()
        shutil.copyfile(pip_wheel, bundled / pip_wheel.name)
        ensurepip_init = ensurepip / "__init__.py"
        ensurepip_init.write_bytes(
            re.sub(
                rb"(?m)^_PIP_VERSION = [^\r\n]+(?=\r?$)",
                f'_PIP_VERSION = "{DOWNLOADS["pip"]["version"]}"'.encode("ascii"),
                ensurepip_init.read_bytes(),
            )
        )

        pcbuild_path = cpython_source_path / "PCbuild"

        out_dir = td / "out"

        build_dir = out_dir / "python" / "build"
        build_dir.mkdir(parents=True)

        # Parse config.c before we hack it up: we want a pristine copy.
        config_c_path = cpython_source_path / "PC" / "config.c"

        with config_c_path.open("r", encoding="utf8") as fh:
            config_c = fh.read()

        builtin_extensions = parse_config_c(config_c)

        hack_project_files(
            cpython_source_path,
            build_directory,
            python_version=python_version,
        )

        if pgo:
            run_msbuild(
                msbuild,
                pcbuild_path,
                dependency_paths,
                configuration="PGInstrument",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
                platform_toolset=platform_toolset,
                freethreaded=freethreaded,
            )

            # build-windows.py sets some environment variables which cause the
            # test harness to pick up the wrong `test` module. We unset these
            # so things work as expected.
            env = dict(os.environ)
            paths = [
                p for p in env["PATH"].split(";") if p != str(BUILD / "venv" / "bin")
            ]
            env["PATH"] = ";".join(paths)
            if "PYTHONPATH" in env:
                del env["PYTHONPATH"]

            env["PYTHONHOME"] = str(cpython_source_path)

            # For some reason, .pgc files aren't being created if we invoke the
            # test harness normally (all tests) or with -j to perform parallel
            # test execution. We work around this by invoking the test harness
            # separately for each test.
            instrumented_python = (
                pcbuild_path
                / pcbuild_directory
                / "instrumented"
                / instrumented_python_exe
            )

            tests = subprocess.run(
                [str(instrumented_python), "-m", "test", "--list-tests"],
                cwd=cpython_source_path,
                env=env,
                check=False,
                stdout=subprocess.PIPE,
            ).stdout

            tests = [l.strip() for l in tests.decode("utf-8").splitlines() if l.strip()]

            for test in sorted(tests):
                # Only look at specific tests, to keep runtime down.
                if test not in PGO_TESTS:
                    continue

                # test_regrtest hangs for some reason. It is the test for the
                # test harness itself and isn't exercising useful code. Skip it.
                if test == "test_regrtest":
                    continue

                exec_and_log(
                    [
                        str(instrumented_python),
                        "-m",
                        "test",
                        # --pgo simply disables some tests, quiets output, and ignores the
                        # exit code. We could disable it if we wanted more verbose test
                        # output...
                        "--pgo",
                        test,
                    ],
                    str(pcbuild_path),
                    env,
                    exit_on_error=False,
                )

            run_msbuild(
                msbuild,
                pcbuild_path,
                dependency_paths,
                configuration="PGUpdate",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
                platform_toolset=platform_toolset,
                freethreaded=freethreaded,
            )
            artifact_config = "PGUpdate"

        else:
            run_msbuild(
                msbuild,
                pcbuild_path,
                dependency_paths,
                configuration="Debug" if debug else "Release",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
                platform_toolset=platform_toolset,
                freethreaded=freethreaded,
            )
            artifact_config = "Debug" if debug else "Release"

        install_dir = out_dir / "python" / "install"

        # The PC/layout directory contains a script for copying files into
        # a release-like directory. Use that for assembling the standalone
        # build.

        # It doesn't clean up the temp directory it creates. So pass one to it
        # under our tempdir.
        layout_tmp = td / "layouttmp"
        layout_tmp.mkdir()

        args = [
            str(cpython_source_path / "python.bat"),
            str(cpython_source_path / "PC" / "layout"),
            "-vv",
            "--source",
            str(cpython_source_path),
            "--build",
            str(pcbuild_path / pcbuild_directory),
            "--copy",
            str(install_dir),
            "--temp",
            str(layout_tmp),
            "--include-dev",
            "--include-symbols",
            "--include-tests",
            "--include-venv",
        ]

        if freethreaded:
            # Creates both versioned and unversioned entry points,
            # includes the _d suffix for debug builds.
            args.extend(["--include-freethreaded", "--include-alias"])

        if debug:
            args.append("--debug")

        if meets_python_minimum_version(python_version, "3.15"):
            args.append("--include-builddetails-json")

        # CPython 3.12 removed distutils.
        if not meets_python_minimum_version(python_version, "3.12"):
            args.append("--include-distutils")

        args.extend(["--include-idle", "--include-stable", "--include-tcltk"])

        exec_and_log(
            args,
            pcbuild_path,
            os.environ,
        )

        # PC/layout omits unsuffixed Tcl/Tk DLLs in debug builds and misses
        # Tcl 9 package directories when its core scripts are embedded in DLLs.
        tcltk_dlls, tcl_library_paths = install_tcltk(
            tcltk_path / build_directory, install_dir
        )

        # We install pip by using pip to install itself. This leverages a feature
        # where Python can automatically recognize wheel/zip files on sys.path and
        # import their contents. According to
        # https://github.com/pypa/pip/issues/11146 running pip from a wheel is not
        # supported. But it has historically worked and is simple. So do this until
        # it stops working and we need to switch to running pip from the filesystem.
        pip_env = dict(os.environ)
        pip_env["PYTHONPATH"] = str(pip_wheel)

        # Install pip and setuptools.
        exec_and_log(
            [
                str(install_dir / python_exe),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-index",
                str(pip_wheel),
            ],
            td,
            pip_env,
        )

        # Setuptools is only installed for Python 3.11 and older, for parity with
        # `ensurepip` and `venv`: https://github.com/python/cpython/pull/101039
        if meets_python_maximum_version(python_version, "3.11"):
            exec_and_log(
                [
                    str(install_dir / python_exe),
                    "-m",
                    "pip",
                    "install",
                    "--no-cache-dir",
                    "--no-index",
                    str(setuptools_wheel),
                ],
                td,
                pip_env,
            )

        # The executables in the Scripts/ directory don't work because they reference
        # python.dll in the wrong path. You can run these via e.g. `python.exe -m pip`.
        # So just delete them for now.
        for filename in sorted(os.listdir(install_dir / "Scripts")):
            assert filename.startswith("pip") and filename.endswith(".exe")
            p = install_dir / "Scripts" / filename
            log(f"removing non-functional executable: {p}")
            os.unlink(p)

        # But this leaves the Scripts directory empty, which we don't want. So
        # create a placeholder file to ensure the directory is created on archive
        # extract.
        with (install_dir / "Scripts" / ".empty").open("ab"):
            pass

        # Now copy the build artifacts into the output directory.
        build_info = collect_python_build_artifacts(
            pcbuild_path,
            out_dir / "python",
            "".join(entry["version"].split(".")[0:2]),
            pcbuild_directory,
            artifact_config,
            openssl_entry=openssl_entry,
            zlib_entry=zlib_entry,
            freethreaded=freethreaded,
            tk_bin_entry=tk_bin_entry,
            tcltk_dlls=tcltk_dlls,
        )

        for ext, init_fn in sorted(builtin_extensions.items()):
            if ext in build_info["extensions"]:
                log(f"built-in extension should not have a build entry: {ext}")
                sys.exit(1)

            build_info["extensions"][ext] = [
                {
                    "in_core": True,
                    "objs": [],
                    "init_fn": init_fn,
                    "links": [],
                    "shared_lib": None,
                    "static_lib": None,
                    "variant": "default",
                }
            ]

        for extension, entries in build_info["extensions"].items():
            for record in entries:
                record["required"] = extension in REQUIRED_EXTENSIONS

        # Copy OpenSSL libraries as a one-off.
        for lib in ("crypto", "ssl"):
            name = f"lib{lib}.lib"

            source = td / "openssl" / build_directory / "lib" / name
            dest = out_dir / "python" / "build" / "lib" / name
            log(f"copying {source} to {dest}")
            shutil.copyfile(source, dest)

        # Use the unversioned entry point supplied by PC/layout. Its _d
        # suffix lets venv and other stdlib code identify debug builds.
        distribution_python_exe = install_dir / f"python{debug_suffix}.exe"

        # CPython 3.13 removed `run_tests.py`, we provide a compatibility script
        # for now.
        if meets_python_minimum_version(python_version, "3.13"):
            shutil.copyfile(
                SUPPORT / "run_tests-13.py",
                out_dir / "python" / "build" / "run_tests.py",
            )
        else:
            shutil.copyfile(
                cpython_source_path / "Tools" / "scripts" / "run_tests.py",
                out_dir / "python" / "build" / "run_tests.py",
            )

        # Install a JSON file annotating tests.
        with (out_dir / "python" / "build" / "stdlib-test-annotations.json").open(
            "w", encoding="utf-8"
        ) as fh:
            test_annotations.json_dump(fh)

        licenses_dir = out_dir / "python" / "licenses"
        licenses_dir.mkdir()
        for f in sorted(os.listdir(ROOT)):
            if f.startswith("LICENSE.") and f.endswith(".txt"):
                shutil.copyfile(ROOT / f, licenses_dir / f)

        extension_module_loading = ["builtin", "shared-library"]

        # Patches to CPython above (search for __declspec) always force
        # __declspec(dllexport), even for static distributions.
        python_symbol_visibility = "dllexport"

        crt_features = ["vcruntime:140"]

        if pgo:
            optimizations = "pgo"
        else:
            optimizations = "noopt"

        # Create PYTHON.json file describing this distribution.
        python_info = {
            "version": "8",
            "target_triple": target_triple,
            "optimizations": optimizations,
            "build_options": build_options,
            "python_tag": entry["python_tag"],
            "python_version": python_version,
            "python_symbol_visibility": python_symbol_visibility,
            "python_stdlib_test_packages": sorted(STDLIB_TEST_PACKAGES),
            "python_extension_module_loading": extension_module_loading,
            "libpython_link_mode": "shared",
            "crt_features": crt_features,
            "build_info": build_info,
            "licenses": entry["licenses"],
            "license_path": "licenses/LICENSE.cpython.txt",
            "run_tests": "build/run_tests.py",
        }

        # Collect information from running Python script.
        metadata_path = td / "metadata.json"
        env = dict(os.environ)
        env["ROOT"] = str(out_dir / "python")
        subprocess.run(
            [
                str(distribution_python_exe),
                str(SUPPORT / "generate_metadata.py"),
                str(metadata_path),
            ],
            env=env,
            check=True,
        )

        with metadata_path.open("rb") as fh:
            metadata = json.load(fh)

        python_info.update(metadata)

        python_info["tcl_library_path"] = "install/tcl"
        python_info["tcl_library_paths"] = tcl_library_paths

        validate_python_json(python_info, extension_modules=None)

        with (out_dir / "python" / "PYTHON.json").open("w", encoding="utf8") as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)

        dest_path = BUILD / (
            f"cpython-{entry['version']}-{target_triple}-{build_options}.tar"
        )

        data = io.BytesIO()
        create_tar_from_directory(data, td / "out")
        data.seek(0)

        data = normalize_tar_archive(data)

        with dest_path.open("wb") as fh:
            while True:
                chunk = data.read(32768)
                if not chunk:
                    break

                fh.write(chunk)

        return dest_path


def fetch_strawberry_perl() -> pathlib.Path:
    strawberryperl_zip = download_entry("strawberryperl", BUILD)
    strawberryperl = BUILD / "strawberry-perl"
    strawberryperl.mkdir(exist_ok=True)
    with zipfile.ZipFile(strawberryperl_zip) as zf:
        zf.extractall(strawberryperl)
    return strawberryperl


def libffi_prepare_sha256(python: str) -> str:
    archive = download_entry(python, BUILD)
    script = f"Python-{DOWNLOADS[python]['version']}/PCbuild/prepare_libffi.bat"
    # Read only this member before cache lookup, including on a cache hit.
    with tarfile.open(archive, "r|*") as tf:
        for member in tf:
            if member.name == script and member.isfile():
                with tf.extractfile(member) as fh:
                    return hashlib.sha256(fh.read()).hexdigest()
    raise FileNotFoundError(f"{script} is missing from {archive}")


def dependency_archive(
    dependency: str, args: argparse.Namespace, build_env: dict[str, str]
) -> pathlib.Path:
    env = {k.upper(): v for k, v in build_env.items()}
    inputs = {
        "target": args.target_triple,
        "vs": args.vs,
        "toolset": args.platform_toolset,
        "vcvars_ver": args.vc_tools_version,
        "sdk": args.windows_sdk_version,
        "resolved_msvc": env["VCTOOLSVERSION"],
        "resolved_sdk": env["WINDOWSSDKVERSION"],
        "environment": {
            name: env.get(name)
            for name in (
                "VCTOOLSINSTALLDIR WINDOWSSDKDIR UCRTVERSION VSCMD_VER IMAGEVERSION "
                "INCLUDE LIB LIBPATH CL _CL_ LINK _LINK_ "
                "AR ARFLAGS AS ASFLAGS CC CFLAGS CXX CXXFLAGS CPP CPPFLAGS CPPDEFINES "
                "CPPINCLUDES CROSS_COMPILE HASHBANGPERL LD LDFLAGS LDLIBS LIBS MT MTFLAGS "
                "PERL RANLIB RC RCFLAGS WINDRES OBJCOPY RM"
            ).split()
        },
    }
    for name in ("cl.exe", "link.exe"):
        path = shutil.which(name, path=env["PATH"])
        if not path:
            raise RuntimeError(f"Visual Studio environment is missing {name}")
        inputs[name] = hash_path(pathlib.Path(path))

    scripts = [SUPPORT / "build.py", ROOT / "pythonbuild" / "utils.py"]
    ci = env.get("GITHUB_ACTIONS") == "true"
    if ci:
        scripts.append(ROOT / ".github" / "workflows" / "windows.yml")
    prefix = dependency
    if dependency == "openssl":
        entries = [
            OPENSSL_ENTRY,
            "nasm-windows-bin",
            "jom-windows-bin",
            "strawberryperl",
        ]
        inputs["uplink"] = args.python == "cpython-3.11"
        if inputs["uplink"]:
            scripts.append(SUPPORT / "patch-openssl-uplink.patch")
    else:
        entries = []
        prepare_sha256 = libffi_prepare_sha256(args.python)
        inputs["prepare_libffi_sha256"] = prepare_sha256
        prefix = f"libffi-{prepare_sha256[:7]}"
        # An unreviewed script could read other files from the same CPython tree.
        if prepare_sha256 not in env.get("PYBUILD_LIBFFI_PREPARE_HASHES", "").split():
            entries.append(args.python)
        inputs["libffi_revision"] = LIBFFI_REVISION
        inputs["sh"] = str(args.sh)
        if ci:
            # The Cygwin installer selects live packages. Share its recipe
            # within one run without installing those packages on consumers.
            inputs["cygwin_run"] = env["GITHUB_RUN_ID"]
            scripts.append(ROOT / "scripts" / "install-cygwin.ps1")
        else:
            scripts.append(args.sh)
            installed = args.sh.parent.parent / "etc" / "setup" / "installed.db"
            if installed.exists():
                scripts.append(installed)

    inputs["sources"] = {
        name: (DOWNLOADS[name]["version"], DOWNLOADS[name]["sha256"])
        for name in entries
    }
    inputs["scripts"] = {p.name: hash_path(p) for p in scripts}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    # Use the full digest for cache lookup even when two short names coincide.
    return BUILD / digest / f"{prefix}-{digest[:7]}.tar"


def ensure_dependency(dependency: str, archive: pathlib.Path, args: argparse.Namespace):
    LOG_PREFIX[0] = dependency
    if archive.is_file():
        log(f"reusing {archive.name}")
        return

    log(f"building {archive.name}")
    arch = TARGET_ARCHITECTURES[args.target_triple]
    # Publish only a complete archive, even if a local build is interrupted.
    archive.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=archive.parent) as td:
        tmp = pathlib.Path(td) / archive.name
        if dependency == "openssl":
            perl_path = fetch_strawberry_perl() / "perl" / "bin" / "perl.exe"
            build_openssl(
                OPENSSL_ENTRY,
                perl_path,
                arch,
                tmp,
                with_uplink=args.python == "cpython-3.11",
            )
        else:
            build_libffi(
                args.python, arch, args.sh, args.vs, args.vc_tools_version, tmp
            )
        tmp.replace(archive)


def main() -> None:
    BUILD.mkdir(exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-triple",
        choices=TARGET_ARCHITECTURES,
        help="Target triple to build for (defaults to the host Python architecture)",
    )
    parser.add_argument(
        "--vs",
        choices={"2019", "2022", "2026"},
        default="2022",
        help="Visual Studio version to use",
    )
    parser.add_argument(
        "--platform-toolset",
        choices=("v143", "v145"),
        help="MSVC toolset (defaults to v145 for x64 CPython 3.15+, otherwise v143)",
    )
    parser.add_argument(
        "--vc-tools-version",
        help="MSVC version or prefix passed to vcvarsall "
        "(defaults to 14.4 for v143 and 14.5 for v145)",
    )
    parser.add_argument(
        "--python",
        choices={
            "cpython-3.11",
            "cpython-3.12",
            "cpython-3.13",
            "cpython-3.14",
            "cpython-3.15",
            "cpython-3.16",
        },
        default="cpython-3.11",
        help="Python distribution to build",
    )
    options = {"debug", "noopt", "pgo"}
    parser.add_argument(
        "--options",
        choices=options.union({f"freethreaded+{o}" for o in options}),
        default="noopt",
        help="Build options to apply when compiling Python",
    )
    parser.add_argument(
        "--sh",
        required=True,
        type=pathlib.Path,
        help="Path to sh.exe in a cygwin or mingw installation",
    )
    parser.add_argument(
        "--dependency", choices=("openssl", "libffi"), help="Build only this dependency"
    )
    parser.add_argument(
        "--write-dependency-keys",
        type=pathlib.Path,
        help="Append relative dependency archive paths to a GitHub Actions output file and exit",
    )
    parser.add_argument(
        "--windows-sdk-version",
        default="10.0.26100.0",
        help="Windows SDK version to build with",
    )

    parser.add_argument(
        "--compression",
        choices=("small", "fast"),
        default="small",
        help="Compression profile for the full distribution archive",
    )

    args = parser.parse_args()
    args.target_triple = args.target_triple or default_target_triple()
    arch = TARGET_ARCHITECTURES[args.target_triple]
    args.platform_toolset = args.platform_toolset or (
        "v145"
        if arch == "amd64"
        and meets_python_minimum_version(DOWNLOADS[args.python]["version"], "3.15")
        else "v143"
    )
    args.vc_tools_version = args.vc_tools_version or (
        "14.5" if args.platform_toolset == "v145" else "14.4"
    )

    log_path = BUILD / "build.log"

    with log_path.open("wb") as log_fh:
        LOG_FH[0] = log_fh

        log(f"building for {args.target_triple}")
        log(f"using {args.platform_toolset} with MSVC {args.vc_tools_version}")
        build_env = get_visual_studio_environment(args.vs, arch, args.vc_tools_version)
        os.environ.update(build_env)
        archives = {}
        for dep in [args.dependency] if args.dependency else ["openssl", "libffi"]:
            dep_env = build_env
            if dep == "libffi" and arch == "arm64":
                # prepare_libffi.bat activates the x86-hosted ARM64 tools.
                dep_env = get_visual_studio_environment(
                    args.vs, "x86_arm64", args.vc_tools_version
                )
            archives[dep] = dependency_archive(dep, args, dep_env)

        if args.write_dependency_keys:
            with args.write_dependency_keys.open("a", encoding="utf-8") as fh:
                for name, archive in archives.items():
                    print(f"{name}={archive.relative_to(BUILD).as_posix()}", file=fh)
            return

        for name, archive in archives.items():
            ensure_dependency(name, archive, args)
        if args.dependency:
            return

        LOG_PREFIX[0] = "cpython"
        tar_path = build_cpython(
            args.python,
            args.target_triple,
            arch,
            build_options=args.options,
            platform_toolset=args.platform_toolset,
            windows_sdk_version=args.windows_sdk_version,
            openssl_archive=archives["openssl"],
            libffi_archive=archives["libffi"],
            openssl_entry=OPENSSL_ENTRY,
        )

        if "PYBUILD_RELEASE_TAG" in os.environ:
            release_tag = os.environ["PYBUILD_RELEASE_TAG"]
        else:
            release_tag = release_tag_from_git()

        # Create, e.g., `cpython-3.11.9+20240224-x86_64-pc-windows-msvc-pgo.tar.zst`.
        DIST.mkdir(exist_ok=True)
        compress_python_archive(
            tar_path,
            DIST,
            f"{tar_path.stem}-{release_tag}",
            compression=args.compression,
        )


if __name__ == "__main__":
    sys.exit(main())
