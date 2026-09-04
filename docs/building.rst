.. _building:

========
Building
========

A Python distribution can be built on a Linux, macOS, or Windows host.
Regardless of the operating system, `uv <https://docs.astral.sh/uv/>`_
must be installed. Additional operating system requirements are outlined
in the following sections.

Regardless of the host, to build a Python distribution::

    $ uv run --no-dev build.py

On Linux and macOS, ``./build.py`` can also be used; it uses
``uv run --no-dev`` via its shebang.

To build a different version of Python::

    $ uv run --no-dev build.py --python cpython-3.14

Various build options can be specified::

    # With profile-guided optimizations (generated code should be faster)
    $ uv run --no-dev build.py --options pgo
    # Produce a debug build.
    $ uv run --no-dev build.py --options debug
    # Produce a free-threaded build without extra optimizations
    $ uv run --no-dev build.py --options freethreaded+noopt

Different platforms support different build options.
``uv run --no-dev build.py --help`` will show the available build options
and other usage information.

Linux
=====

The host system must be x86-64 or aarch64. The execution environment must
have access to a Docker daemon (all build operations are performed in
Docker containers for isolation from the host system). Docker Buildx must
be installed and available as ``docker buildx``.

``build.py`` accepts a ``--target-triple`` argument to support building
for non-native targets (i.e., cross-compiling).

This option can be used to build for musl libc::

    $ ./build.py --target-triple x86_64-unknown-linux-musl

Or on an x86-64 host for different architectures::

    $ ./build.py --target-triple armv7-unknown-linux-gnueabi
    $ ./build.py --target-triple armv7-unknown-linux-gnueabihf
    $ ./build.py --target-triple ppc64le-unknown-linux-gnu
    $ ./build.py --target-triple riscv64-unknown-linux-gnu
    $ ./build.py --target-triple s390x-unknown-linux-gnu

Jessie image package authentication
-----------------------------------

The ``build``, ``gcc``, and ``rust`` Dockerfiles include
``cpython-unix/base.Dockerfile``. These amd64 images use Debian Jessie
for build compatibility. Cross-compilation targets also use the ``gcc``
image for toolchain builds.

Building these images requires Docker Buildx with support for Dockerfile
1.6's ``ADD --checksum`` instruction.

The base Dockerfile pins the SHA-256 digests of the three archived
``Packages.gz`` indexes because Jessie's archive signing keys have expired.
Docker fetches them over HTTPS and verifies their digests before APT uses
them. APT then verifies downloaded packages against the hashes in these
fixed indexes. ``trusted=yes`` permits this separate trust root;
``apt-get update`` is blocked to prevent replacing the pinned indexes with
unauthenticated metadata.

The pinned base image lacks both ``apt-transport-https`` and
``ca-certificates``. Their bootstrap download uses HTTP, authenticated by
the pinned package hashes. Once they are installed, subsequent package
downloads use HTTPS with certificate verification.

The index digests come from the SHA256 sections of the archived
`Jessie Release <https://snapshot.debian.org/archive/debian/20230322T152120Z/dists/jessie/Release>`_,
`Jessie updates Release <https://snapshot.debian.org/archive/debian/20230322T152120Z/dists/jessie-updates/Release>`_, and
`Jessie security Release <https://snapshot.debian.org/archive/debian-security/20230322T152120Z/dists/jessie/updates/Release>`_
files. The corresponding archive key fingerprints in the digest-pinned
base image are ``126C0D24BD8A2942CC7DF8AC7638D0442B90D010``
for Jessie and Jessie updates, and
``D21169141CECD440F2EB8DDA9D6D8F6BC857C906`` for Jessie security. Any change
to the snapshot or index digests requires independently authenticating the
replacement metadata.

macOS
=====

The Xcode command-line tools must be installed.
``/usr/bin/clang`` must exist.

macOS SDK headers must be installed. If you see errors such as ``stdio.h``
not being found, try running ``xcode-select --install`` to install them.
Verify they are installed by running ``xcrun --show-sdk-path``. It should
print something like
``/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk``
on modern versions of macOS.

The ``--target-triple`` argument can be used to build for an Intel Mac on
an arm64 (Apple Silicon) host::

    $ ./build.py --target-triple x86_64-apple-darwin

Additionally, an arm64 macOS host can be used to build Linux aarch64 and x86-64
targets using Docker::

    $ ./build.py --target-triple aarch64-unknown-linux-gnu
    $ ./build.py --target-triple x86_64-unknown-linux-gnu

The ``APPLE_SDK_PATH`` environment variable is recognized as the path
to the Apple SDK to use. If not defined, the build will attempt to find
an SDK by running ``xcrun --show-sdk-path``.

``aarch64-apple-darwin`` builds require a macOS 11.0+ SDK.
It should be possible to build for ``aarch64-apple-darwin`` from
an Intel 10.15 machine (as long as the 11.0+ SDK is used).

Windows
=======

Visual Studio 2022 (or later) is required. For ``x86_64-pc-windows-msvc``
targets, use Visual Studio 2026 when building CPython 3.15 or newer. The
``i686-pc-windows-msvc`` and ``aarch64-pc-windows-msvc`` targets continue
to use Visual Studio 2022.
A compatible Windows SDK is required (10.0.26100.0 as of CPython 3.10).
A ``git.exe`` must be on ``PATH`` (to clone ``libffi`` from source).
Cygwin must be installed with the ``autoconf``, ``automake``, ``libtool``,
and ``make`` packages, which are required to build ``libffi``.

Building can be done from the ``x64 Native Tools Command Prompt``, by calling
the vcvars batch file, or by adjusting the ``PATH`` and environment variables.

You will need to specify the path to ``sh.exe`` from Cygwin::

   $ uv run --no-dev build.py --sh c:\cygwin\bin\sh.exe

When using a version of Visual Studio other than 2022, the version must
be specified with the ``--vs`` option. For example, to build CPython 3.15
with Visual Studio 2026::

   $ uv run --no-dev build.py --sh c:\cygwin\bin\sh.exe --vs 2026 --python cpython-3.15

To build a 32-bit x86 binary, simply use an
``x86 Native Tools Command Prompt`` instead of ``x64``.
