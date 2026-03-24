.. _building:

========
Building
========

A Python distribution can be built on a Linux, macOS or Windows host.
Regardless of the operating system, `uv <https://docs.astral.sh/uv/>`_ must be installed. 
Additional operating system requirements are needed and outlined in the following sections.

Regardless of the host, to build a Python distribution::

    $ uv run build.py

On Linux and macOS, ``./build.py`` can also be used.

To build a different version of Python::

    $ uv run build.py --python cpython-3.14

Various build options can be specified::

    # With profile-guided optimizations (generated code should be faster)
    $ uv run build.py --options pgo
    # Produce a debug build.
    $ uv run build.py --options debug
    # Produce a free-threaded build without extra optimizations
    $ uv run build.py --options freethreaded+noopt

Different platforms  support different build options. 
``uv run build.py --help`` will show the available build options and other usage information.


Linux
=====

The host system must be x86-64 or aarch64. 
The execution environment must have access to a Docker
daemon (all build operations are performed in Docker containers for
isolation from the host system).

``build.py`` accepts a ``--target-triple`` argument to support building
for non-native targets (i.e. cross-compiling). 

This option can be used to build for musl libc::

    $ ./build.py --target-triple x86_64-unknown-linux-musl

Or on a x86-64 host for different architectures::

    $ ./build.py --target-triple i686-unknown-linux-gnu
    $ ./build.py --target-triple armv7-unknown-linux-gnueabi
    $ ./build.py --target-triple armv7-unknown-linux-gnueabihf
    $ ./build.py --target-triple loongarch64-unknown-linux-gnu
    $ ./build.py --target-triple mips-unknown-linux-gnu
    $ ./build.py --target-triple mipsel-unknown-linux-gnu
    $ ./build.py --target-triple ppc64le-unknown-linux-gnu
    $ ./build.py --target-triple riscv64-unknown-linux-gnu
    $ ./build.py --target-triple s390x-unknown-linux-gnu


macOS
=====

The XCode command line tools must be installed.
``/usr/bin/clang`` must exist.

macOS SDK headers must be installed. 
If you see errors such as ``stdio.h`` not being found, try running ``xcode-select --install`` to install them.
Verify they are installed by running ``xcrun --show-sdk-path``.
It should print something like
``/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk``
on modern versions of macOS.

The ``--target-triple`` argument can be used to build for an Intel Mac on an arm64 (Apple Silicon) host::

    $ ./build.py --target-triple x86_64-apple-darwin

Additionally, an arm64 macOS host can be used to build Linux aarch64 targets using Docker::

    $ ./build.py --target-triple aarch64-unknown-linux-gnu

The ``APPLE_SDK_PATH`` environment variable is recognized as the path
to the Apple SDK to use. If not defined, the build will attempt to find
an SDK by running ``xcrun --show-sdk-path``.

``aarch64-apple-darwin`` builds require a macOS 11.0+ SDK.
It should be possible to build for ``aarch64-apple-darwin`` from
an Intel 10.15 machine (as long as the 11.0+ SDK is used).

Windows
=======

Visual Studio 2022 (or later) is required. 
A compatible Windows SDK is required (10.0.26100.0 as of CPython 3.10).
A ``git.exe`` must be on ``PATH`` (to clone ``libffi`` from source).
Cygwin must be installed with the ``autoconf``, ``automake``, ``libtool``,
and ``make`` packages. (``libffi`` build dependency.)

Building can be done from the ``x64 Native Tools Command Prompt``, by calling 
the vcvars batch file, or by adjusting the ``PATH`` and environment variables.

You will need to specify the path to ``sh.exe`` from cygwin::

   $ uv run build.py --sh c:\cygwin\bin\sh.exe

To build a 32-bit x86 binary, simply use an ``x86 Native Tools Command Prompt`` instead of ``x64``.