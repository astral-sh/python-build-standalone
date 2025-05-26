.. _building:

========
Building
========

Linux
=====

The host system must be 64-bit. A Python 3.9+ interpreter must be
available. The execution environment must have access to a Docker
daemon (all build operations are performed in Docker containers for
isolation from the host system).

To build a Python distribution for Linux x64::

    $ ./build-linux.py
    # With profile-guided optimizations (generated code should be faster):
    $ ./build-linux.py --options pgo
    # Produce a debug build.
    $ ./build-linux.py --options debug
    # Produce a free-threaded build without extra optimizations
    $ ./build-linux.py --options freethreaded+noopt

You can also build another version of Python. e.g.::

    $ ./build-linux.py --python cpython-3.13

To build a Python distribution for Linux x64 using musl libc::

    $ ./build-linux.py --target x86_64-unknown-linux-musl

Building a 32-bit x86 Python distribution is also possible::

    $ ./build-linux.py --target i686-unknown-linux-gnu

As are various other targets::

    $ ./build-linux.py --target aarch64-unknown-linux-gnu
    $ ./build-linux.py --target armv7-unknown-linux-gnueabi
    $ ./build-linux.py --target armv7-unknown-linux-gnueabihf
    $ ./build-linux.py --target mips-unknown-linux-gnu
    $ ./build-linux.py --target mipsel-unknown-linux-gnu
    $ ./build-linux.py --target ppc64le-unknown-linux-gnu
    $ ./build-linux.py --target riscv64-unknown-linux-gnu
    $ ./build-linux.py --target s390x-unknown-linux-gnu

macOS
=====

The XCode command line tools must be installed. A Python 3 interpreter
is required to execute the build. ``/usr/bin/clang`` must exist.

macOS SDK headers must be installed. Try running ``xcode-select --install``
to install them if you see errors about e.g. ``stdio.h`` not being found.
Verify they are installed by running ``xcrun --show-sdk-path``. It
should print something like
``/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk``
on modern versions of macOS.

To build a Python distribution for macOS::

    $ ./build-macos.py

macOS uses the same build code as Linux, just without Docker.
So similar build configuration options are available.

``build-macos.py`` accepts a ``--target-triple`` argument to support building
for non-native targets (i.e. cross-compiling). By default, macOS builds target
the currently running architecture. e.g. an Intel Mac will target
``x86_64-apple-darwin`` and an M1 (ARM) Mac will target ``aarch64-apple-darwin``.
It should be possible to build an ARM distribution on an Intel Mac and an Intel
distribution on an ARM Mac.

The ``APPLE_SDK_PATH`` environment variable is recognized as the path
to the Apple SDK to use. If not defined, the build will attempt to find
an SDK by running ``xcrun --show-sdk-path``.

``aarch64-apple-darwin`` builds require a macOS 11.0+ SDK.
It should be possible to build for ``aarch64-apple-darwin`` from
an Intel 10.15 machine (as long as the 11.0+ SDK is used).

Windows
=======

Visual Studio 2017 (or later) is required. A compatible Windows SDK is required
(10.0.17763.0 as per CPython 3.7.2).

* A ``git.exe`` on ``PATH`` (to clone ``libffi`` from source).
* An installation of Cywgin with the ``autoconf``, ``automake``, ``libtool``,
  and ``make`` packages installed. (``libffi`` build dependency.)

To build a dynamically linked Python distribution for Windows x64::

    $ py.exe build-windows.py --options noopt

It's also possible to build with optional PGO optimizations::

   $ py.exe build-windows.py --options pgo

You will need to specify the path to a ``sh.exe`` installed from cygwin. e.g.

   $ py.exe build-windows.py --python cpython-3.13 --sh c:\cygwin\bin\sh.exe --options noopt

To build a 32-bit x86 binary, simply use an ``x86 Native Tools
Command Prompt`` instead of ``x64``.
