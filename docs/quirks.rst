.. _quirks:

===============
Behavior Quirks
===============

.. _quirk_backspace_key:

Backspace Key Doesn't work in Python REPL
=========================================

If you attempt to run ``python`` and the backspace key doesn't
erase characters or the arrow keys don't work as expected, this
is because the executable can't find the *terminfo database*.

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

Because python-build-standalone Python distributions compile
and use their own version of ``readline``/``libedit`` and
because the build environment is different from your
machine, the default search locations for the *terminfo
database* built into binaries distributed with this project
may point to a path that doesn't exist. The *terminfo database*
cannot be located and ``readline``/``libedit`` do not know
how to convert special key presses to special behavior.

The solution to this is to set an environment variable
with the location of the *terminfo database*.

If running a Debian based Linux distribution (including Ubuntu)::

   $ TERMINFO_DIRS=/etc/terminfo:/lib/terminfo:/usr/share/terminfo

If running a RedHat based Linux distribution::

   $ TERMINFO_DIRS=/etc/terminfo:/usr/share/terminfo

If running macOS::

   $ TERMINFO_DIRS=/usr/share/terminfo

e.g.::

   $ TERMINFO_DIRS=/etc/terminfo:/lib/terminfo:/usr/share/terminfo install/bin/python3.9

The macOS distributions built with this project should automatically
use the terminfo database in ``/usr/share/terminfo``. Please file
a bug report if the macOS distributions do not behave as expected.

.. _quirk_tcl:

Tcl/tk Support Files
====================

Python functionality using tcl/tk (such as the ``tkinter`` or ``turtle``
modules) requires loading ``.tcl`` support files from the filesystem.
If these support files cannot be found, you'll get an error like
``_tkinter.TclError: Can't find a usable init.tcl in the following
directories:``.

Distributions produced from this project contain tcl/tk support files.
The paths to these files in the extracted distribution are advertised
in the ``PYTHON.json`` file.

When tcl is initialized by Python, Python and tcl attempt to locate the
``.tcl`` support files. If the ``tcl<X.Y>/init.tcl`` file cannot be found,
an error occurs.

But the mechanism for finding the ``.tcl`` files varies by platform.

On all platforms, if the ``TCL_LIBRARY`` environment variable is set,
it will be used to locate the ``.tcl`` support files. This environment
variable is processed by tcl itself and is documented at
https://wiki.tcl-lang.org/page/TCL_LIBRARY.

On Windows, CPython will attempt to locate the ``.tcl`` support files in
well-defined directories. The C code performs the equivalent of the
following:

.. code-block:: python

   import os
   import sys

   def get_tcl_path():
       # e.g. sys.prefix/tcl/tcl8.6
       p = os.path.join(sys.prefix, "tcl", "tcl<X.Y>")
       if os.path.exists(p):
           return p

       return None

If Python's code can find the support files in the well-defined location,
it calls into the tcl C API and defines the ``tcl_library`` variable to the
found path.

The most robust way to ensure Python/tcl can find the ``.tcl`` support files
is to define ``TCL_LIBRARY`` to the path to the ``.tcl`` files present in
the extracted Python distribution. It is possible to define this environment
variable from within Python. But it must be done before running any Python
code in the ``tkinter`` module. The following example should work on Linux
and macOS distributions:

.. code-block:: python

   import os
   import sys

   os.environ["TCL_LIBRARY"] = os.path.join(os.path.dirname(sys.executable), "..", "lib", "tcl8.6")

   import turtle

If you don't set ``TCL_LIBRARY`` on Linux and macOS, the default search
mechanics implemented by Tcl are used. These may pick up ``.tcl`` files from
a location outside the Python distribution. This may *just work*. This may
fail fast. Or it could result in undefined behavior. For best results,
forcefully point Tcl at the ``.tcl`` files from the Python distribution
produced by this project.

On Windows, explicitly setting ``TCL_LIBRARY`` is not required as the
default install layout of this project's Python distributions allows CPython's
filesystem probing code to find the ``.tcl`` files. As long as the
files from ``python/install/tcl`` are present (in a ``tcl`` directory
under the directory where the ``python.exe`` is), things should *just work*.

For reference, PyOxidizer's approach to this problem is to copy all the
``.tcl`` files from the Python distribution into an install location. At
run time, the ``TCL_LIBRARY`` environment variable is set from within
the process before the Python interpreter is initialized. This ensures the
``.tcl`` files from the Python distribution are used.

.. _quirk_macos_no_tix:

No tix on macOS
===============

macOS distributions do not contain tix tcl support files. This means that
``tkinter.tix`` module functionality will likely break at run-time. The
module will import fine. But attempting to instantiate a ``tkinter.tix.Tk``
instance or otherwise attempt to run tix tcl files will result in a run-time
error.

``tkinter.tix`` has been deprecated since Python 3.6 and the official Python
macOS installers do not ship the tix support files. So this project behaves
similarly to the official CPython distributions.

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

.. _quirk_windows_static_distributions:

Windows Static Distributions are Extremely Brittle
==================================================

This project produces statically linked CPython distributions for Windows.

Building these distributions requires extensive patching of CPython's build
system. There are many aspects of CPython, the standard library, and 3rd party
libraries that make assumptions that things will be built as dynamic libraries
and break in these static builds.

Here is a list of known problems:

* Most Windows extension modules link against ``pythonXY.dll`` (e.g.
  ``python39.dll``) or ``python3.dll`` and will fail to load on the static
  distributions. Extension modules will need to be explicitly recompiled
  against the static distribution.
* There is no supported *platform tag* for Windows static distributions and
  therefore there is no supported way to distribute binary wheels targeting
  the Python static distributions.
* Aspects of OpenSSL (and therefore Python's ``ssl`` module) don't work when
  OpenSSL is compiled/linked statically. You will get opaque run-time errors.

It is **highly** recommended to extensively test your application against the
static Windows distributions to ensure it works.

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

Static Linking of musl libc Prevents Extension Module Library Loading
=====================================================================

Our musl libc linked Linux builds link musl libc statically and the resulting
binaries are completely static and don't have any external dependencies.

Due to how Linux/ELF works, a static/non-dynamic binary cannot call
``dlopen()`` and therefore it cannot load shared library based Python
extension modules (``.so`` based extension modules). This significantly
limits the utility of these Python distributions. (If you want to use
additional extension modules you can use the build artifacts in the
distributions to construct a new ``libpython`` with the additional
extension modules configured as builtin extension modules.)

Another consequence of statically linking musl libc is that our musl
distributions aren't compatible with
`PEP 656 <https://www.python.org/dev/peps/pep-0656/>`_. PEP 656
stipulates that Python and extension modules are linked against a
dynamic musl. This is what you'll find in Alpine Linux, for example.

See https://github.com/indygreg/python-build-standalone/issues/86 for
a tracking issue to improve the state of musl distributions.

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
occur. See e.g. https://github.com/indygreg/python-build-standalone/issues/95.

The conceptual workaround is to not statically link ``libX11`` and similar
libraries into ``libpython``. However, this requires re-linking a custom
``libpython`` without ``_tkinter``. It is possible to do this with the object
files included in the distributions. But there isn't a turnkey way to do this.
And you can't easily remove ``_tkinter`` and its symbols from the pre-built
and ready-to-use Python install included in this project's distribution
artifacts.
