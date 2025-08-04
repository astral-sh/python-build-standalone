.. _quirks:

===============
Behavior Quirks
===============

While these Python distributions are intended to be broadly compatible
with the Python ecosystem, there are a few known behavior quirks that
affect specific environments, packages, or use cases.

.. _quirk_backspace_key:

If special keys do not work in the Python REPL
==============================================

If you attempt to run ``python`` and the backspace key doesn't
erase characters or the arrow keys don't work as expected, this
is because the executable can't find the *terminfo database*.

If this happens, the Python REPL will print the following warning
message on startup::

   Cannot read termcap database;
   using dumb terminal settings.

When you type a special key like the backspace key, this is
registered as a key press. There is special software (typically
``readline`` or ``libedit``) that most interactive programs use
that intercepts these special key presses and converts them into
special behavior, such as moving the cursor back instead of
forward. But because computer environments are different,
there needs to be some definition of how these special
behaviors are performed. This is the *terminfo database*.

When ``readline`` and ``libedit`` are compiled, there is
typically a hard-coded set of search locations for the
*terminfo database* baked into the built library. And when
you build a program (like Python) locally, you link against
``readline`` or ``libedit`` and get these default locations
*for free*.

These Python distributions compile and use their own version of
``libedit`` to avoid a dependency on what is (or isn't) installed on
your system. This means that they do not use your system-provided
libraries for reading the *terminfo database*.  This version of
``libedit`` is configured to look for in locations that should work for
most OSes (specifically, ``/usr/share/terminfo`` on macOS, and
``/etc/terminfo``, ``/lib/terminfo``, and ``/usr/share/terminfo`` on
Linux, which should cover all major Linux distributions), but it is
possible that your environment has it somewhere else. If your OS stores
the *terminfo database* in an uncommon location, you can set the
``TERMINFO_DIRS`` environment variable so that ``libedit`` can find it.

For instance, you may need to do something like:

   $ TERMINFO_DIRS=/uncommon/place/terminfo install/bin/python3.9

If you are running on a relatively standard OS and this does not work
out of the box, please file a bug report so we can add the location of
the *terminfo database* to the build.

For convenience, a relatively recent copy of the terminfo database
is distributed in the ``share/terminfo`` directory (``../../share/terminfo``
relative to the ``bin/python3`` executable) in Linux distributions. Note
that ncurses and derived libraries don't know how to find this directory
since they are configured to use absolute paths to the terminfo database
and the absolute path of the Python distribution is obviously not known
at build time! So actually using this bundled terminfo database will
require custom code setting ``TERMINFO_DIRS`` before
ncurses/libedit/readline are loaded.

.. _quirk_macos_no_tix:

No tix on UNIX
==============

Tix is an old widget library for Tcl/Tk. Python previously had a wrapper
for it in ``tkinter.tix``, but it was deprecated in Python 3.6 (the
recommendation is to use ``tkinter.ttk``) and removed in Python 3.13.

The macOS and Linux distributions from this project do not build and
ship Tix, even for Python versions 3.12 and below.

We had previously attempted to ship Tix support on Linux, but it was
broken and nobody reported an issue about it. The macOS distributions
from this project never shipped support for Tix. The official Python.org
macOS installers and Apple's build of Python do not ship support for
Tix, either, so this project behaves similarly to those distributions.

.. _quirk_windows_no_pip:

No ``pip.exe`` on Windows
=========================

The Windows distributions have ``pip`` installed however no ``Scripts/pip.exe``,
``Scripts/pip3.exe``, and ``Scripts/pipX.Y.exe`` files are provided because
the way these executables are built isn't portable. (It might be possible to
change how these are built to make them portable.)

To use pip, run ``python.exe -m pip``. (It is generally a best practice to
invoke pip via ``python -m pip`` on all platforms so you can be explicit
about the ``python`` executable that pip uses.)

.. _quirk_macos_linking:

Linking Static Library on macOS
===============================

Python 3.9+ makes use of the ``__builtin_available()`` compiler feature.
This functionality requires a symbol from ``libclang_rt``, which may not
be linked by default. Failure to link against ``libclang_rt`` could result
in a linker error due to an undefined symbol ``___isOSVersionAtLeast``.

To work around this linker failure, link against the static library
``libclang_rt.<platform>.a`` present in the Clang installation. e.g.
``libclang_rt.osx.a``. You can find this library by invoking
``clang --print-search-dirs`` and looking in the ``lib/darwin`` directory
under the printed ``libraries`` directory. An example path is
``/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang/12.0.0/lib/darwin/libclang_rt.osx.a``.

A copy of the ``libclang_rt.<platform>.a`` from the Clang used to build
the distribution is included in the archive. However, it isn't annotated
in ``PYTHON.json`` because we're unsure if using the file with another
build/version of Clang is supported. Use at your own risk.

See https://jonnyzzz.com/blog/2018/06/05/link-error-2/ and
https://jonnyzzz.com/blog/2018/06/13/link-error-3/ for more on this topic.

.. _quirk_linux_libedit:

Use of ``libedit`` on Linux
===========================

Python 3.10+ Linux distributions link against ``libedit`` (as opposed to
``readline``) by default, as ``libedit`` is supported on 3.10+ outside of
macOS.

Most Python builds on Linux will link against ``readline`` because ``readline``
is the dominant library on Linux.

Some functionality may behave subtly differently as a result of our choice
to link ``libedit`` by default. (We choose ``libedit`` by default to
avoid GPL licensing requirements of ``readline``.)

.. _quirk_linux_libx11:

Static Linking of ``libX11`` / Incompatibility with PyQt on Linux
=================================================================

The ``_tkinter`` Python extension module in the Python standard library
statically links against ``libX11``, ``libxcb``, and ``libXau`` on Linux.
In addition, the ``_tkinter`` extension module is statically linked into
``libpython`` and isn't a standalone shared library file. This effectively
means that all these X11 libraries are statically linked into the main
Python interpreter.

On typical builds of Python on Linux, ``_tkinter`` will link against
external shared libraries. e.g.::

   $ ldd /usr/lib/python3.9/lib-dynload/_tkinter.cpython-39-x86_64-linux-gnu.so
        linux-vdso.so.1 (0x00007fff3be9d000)
        libBLT.2.5.so.8.6 => /lib/libBLT.2.5.so.8.6 (0x00007fdb6a6f8000)
        libtk8.6.so => /lib/x86_64-linux-gnu/libtk8.6.so (0x00007fdb6a584000)
        libtcl8.6.so => /lib/x86_64-linux-gnu/libtcl8.6.so (0x00007fdb6a3c1000)
        libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007fdb6a1d5000)
        libX11.so.6 => /lib/x86_64-linux-gnu/libX11.so.6 (0x00007fdb6a097000)
        libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007fdb69f49000)
        libXft.so.2 => /lib/x86_64-linux-gnu/libXft.so.2 (0x00007fdb69f2e000)
        libfontconfig.so.1 => /lib/x86_64-linux-gnu/libfontconfig.so.1 (0x00007fdb69ee6000)
        libXss.so.1 => /lib/x86_64-linux-gnu/libXss.so.1 (0x00007fdb69ee1000)
        libdl.so.2 => /lib/x86_64-linux-gnu/libdl.so.2 (0x00007fdb69eda000)
        libz.so.1 => /lib/x86_64-linux-gnu/libz.so.1 (0x00007fdb69ebe000)
        libpthread.so.0 => /lib/x86_64-linux-gnu/libpthread.so.0 (0x00007fdb69e9c000)
        /lib64/ld-linux-x86-64.so.2 (0x00007fdb6a892000)
        libxcb.so.1 => /lib/x86_64-linux-gnu/libxcb.so.1 (0x00007fdb69e70000)
        libfreetype.so.6 => /lib/x86_64-linux-gnu/libfreetype.so.6 (0x00007fdb69dad000)
        libXrender.so.1 => /lib/x86_64-linux-gnu/libXrender.so.1 (0x00007fdb69da0000)
        libexpat.so.1 => /lib/x86_64-linux-gnu/libexpat.so.1 (0x00007fdb69d71000)
        libuuid.so.1 => /lib/x86_64-linux-gnu/libuuid.so.1 (0x00007fdb69d68000)
        libXext.so.6 => /lib/x86_64-linux-gnu/libXext.so.6 (0x00007fdb69d53000)
        libXau.so.6 => /lib/x86_64-linux-gnu/libXau.so.6 (0x00007fdb69d4b000)
        libXdmcp.so.6 => /lib/x86_64-linux-gnu/libXdmcp.so.6 (0x00007fdb69d43000)
        libpng16.so.16 => /lib/x86_64-linux-gnu/libpng16.so.16 (0x00007fdb69d08000)
        libbrotlidec.so.1 => /lib/x86_64-linux-gnu/libbrotlidec.so.1 (0x00007fdb69cfa000)
        libbsd.so.0 => /lib/x86_64-linux-gnu/libbsd.so.0 (0x00007fdb69ce2000)
        libbrotlicommon.so.1 => /lib/x86_64-linux-gnu/libbrotlicommon.so.1 (0x00007fdb69cbd000)
        libmd.so.0 => /lib/x86_64-linux-gnu/libmd.so.0 (0x00007fdb69cb0000)

The static linking of ``libX11`` and other libraries can cause problems when
3rd party Python extension modules also loading similar libraries are also
loaded into the process. For example, extension modules associated with ``PyQt``
are known to link against a shared ``libX11.so.6``. If multiple versions of
``libX11`` are loaded into the same process, run-time crashes / segfaults can
occur. See e.g. https://github.com/astral-sh/python-build-standalone/issues/95.

The conceptual workaround is to not statically link ``libX11`` and similar
libraries into ``libpython``. However, this requires re-linking a custom
``libpython`` without ``_tkinter``. It is possible to do this with the object
files included in the distributions. But there isn't a turnkey way to do this.
And you can't easily remove ``_tkinter`` and its symbols from the pre-built
and ready-to-use Python install included in this project's distribution
artifacts.

.. _quirk_references_to_build_paths:

References to Build-Time Paths
==============================

The built Python distribution captures some absolute paths and other
build-time configuration in a handful of files:

* In a ``_sysconfigdata_*.py`` file in the standard library. e.g.
  ``lib/python3.10/_sysconfigdata__linux_x86_64-linux-gnu.py``.
* In a ``Makefile`` under a ``config-*`` directory in the standard library.
  e.g. ``lib/python3.10/config-3.10-x86_64-linux-gnu/Makefile``.
* In python-build-standalone's metadata file ``PYTHON.json`` (mostly
  reflected values from ``_sysconfigdata_*.py``).

Each of these serves a different use case. But the general theme is various
aspects of the Python distribution attempt to capture how Python was built.
The most common use of these values is to facilitate compiling or linking
other software against this Python build. For example, the ``_sysconfigdata*``
module is loaded by the `sysconfig <https://docs.python.org/3/library/sysconfig.html>`_
module. ``sysconfig`` in turn is used by packaging tools like ``setuptools``
and ``pip`` to figure out how to invoke a compiler for e.g. compiling C
extensions from source.

When installed by `uv <https://docs.astral.sh/uv/>`_, these absolute
paths are fixed up to point to the actual location on your system where
the distribution was installed, so **this quirk generally does not
affect uv users**.  The third-party tool `sysconfigpatcher
<https://github.com/bluss/sysconfigpatcher>`_ also does this and might
be helpful to use or reference if you are installing these distributions
on your own.

In particular, you may see references to our install-time paths on the
build infrastructure, e.g., ``/build`` and ``/install`` on Linux, a
particular SDK in ``/Applications/Xcode.app`` on macOS, and temporary
directories on Windows.

Also, Python reports the compiler and flags in use, just in case it is
needed to make binary-compatible extensions. On Linux, for instance, we
use our own builds of Clang and potentially some flags (warnings,
optimizations, locations of the build environment) that do not work or
apply in other environments.  We try to configure Python to remove
unneeded flags and absolute paths to files in the build environment.
references to build-time paths.  Python's ``sysconfig`` system requires
listing a compiler, so we leave it set to ``clang`` without the absolute
path, but you should be able to use another compiler like ``gcc`` to
compile extensions, too.

If there is a build time normalization that you think should be performed to
make distributions more portable, please file a GitHub issue.

.. _quirk_former:
.. _quirk_missing_libcrypt:

Former quirks
=============

The following quirks were previously listed on this page but have since
been resolved.

* "Static Linking of musl libc Prevents Extension Module Library
  Loading": Starting with the 20250311 release, the default musl
  distributions are dynamically linked by default, so extension modules
  should work properly. Note that these now require a system-wide
  installation of the musl C library. (This is present by default on
  musl-based OSes like Alpine, and many glibc-based distros have a
  ``musl`` package you can safely co-install with glibc, too.) If you
  specifically need a statically-linked binary, variants with the
  ``+static`` build option are available, but these retain the quirk
  that compiled extension modules (e.g., ``musllinux`` wheels) cannot be
  loaded.

* "Missing ``libcrypt.so.1``": The 20230507 release and earlier required
  the system library ``libcrypt.so.1``, which stopped being shipped by
  default in several Linux distributions around 2022. Starting with the
  20230726 release, this dependency is now only needed by the deprecated
  ``crypt`` module, which only exists on Python 3.12 and lower. If you
  still need this module, your OS may offer a ``libxcrypt`` package to
  provide this library. Alternatively, there are suggestions in `What's
  New in Python 3.13`_ about third-party replacements for the ``crypt``
  module.

.. _What's New in Python 3.13: https://docs.python.org/3/whatsnew/3.13.html#whatsnew313-pep594
