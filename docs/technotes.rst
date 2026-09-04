.. _technotes:

===============
Technical Notes
===============

How It Works
============

The first thing the ``build.py`` scripts do is bootstrap an environment
for building Python. Linux builds use Docker images based on deterministic
Debian snapshots selected for each target:

* x86-64 targets use Debian Jessie and a prebuilt Clang toolchain.
* aarch64 targets use Debian Stretch and a prebuilt Clang toolchain.
* Other cross-compiled targets generally use Debian Stretch and
  Debian-provided GCC cross-compilers.
* riscv64 targets use Debian Buster and a Debian-provided GCC
  cross-compiler.

The selected toolchain is used to build Python's dependencies (OpenSSL,
ncurses, libedit, SQLite, etc.). Finally, Python itself is built.

Python is built in such a way that extensions are statically linked
against their dependencies. For example, instead of the ``sqlite3`` Python
extension having a run-time dependency against ``libsqlite3.so``, the
SQLite symbols are statically inlined into the Python extension object
file. Extension modules are statically linked into ``python`` rather than
provided as shared extensions in the ``lib-dynload`` directory.

``_dbm`` and ``_tkinter`` are handled differently. On dynamically linked
Linux builds, ``_dbm`` is provided as a shared extension with Berkeley DB
statically linked. This allows the module to be easily removed when the
Berkeley DB license is undesired (see the DBM section below). On macOS,
``_dbm`` instead uses the system NDBM implementation. ``_tkinter`` is
also provided as a shared extension, with Tcl and Tk dynamically linked,
on builds that support shared extensions.

From the built Python, we produce an archive containing the raw Python
distribution (as if you had run ``make install``) as well as other files
useful for downstream consumers.

Setup.local Hackery
===================

Starting with Python 3.12, C extension modules are configured and built
using ``configure``, ``Modules/Setup.stdlib``, and ``Makefile``. A
generated ``Modules/Setup.local`` file disables selected modules and
overrides whether others are linked statically or built as shared
libraries.

Prior to 3.12, many extensions were configured and built using ``setup.py``
scripts. These scripts do not provide much flexibility and rely on default
behaviors in ``distutils``, as well as other inline code in ``setup.py``.
This default behavior is often undesirable for our desired outcome of
producing a standalone Python distribution.

Because of this, when building Python prior to 3.12, a custom ``Setup.local``
file is generated that builds all C extensions in a specific manner.
The undesirable behavior of ``setup.py`` is bypassed and the Python C
extensions are compiled just the way we want.

Dependency Notes
================

DBM
---

Python has the option of building its ``_dbm`` extension against NDBM,
GDBM, and Berkeley DB. GDBM and its NDBM compatibility libraries are
licensed under GNU GPL Version 3. Modern versions of Berkeley DB are
licensed under GNU AGPL v3. Versions 6.0.19 and older are licensed under
the more permissive Sleepycat License.

On Linux, we build the ``_dbm`` extension against Berkeley DB 6.0.19. On
macOS, ``_dbm`` uses the NDBM implementation provided by the system
``libSystem`` library instead.

We explicitly disable the ``_gdbm`` extension on all targets to avoid
the GPL dependency.

readline / libedit / ncurses
----------------------------

Python has the option of building its ``readline`` extension against
either ``libreadline`` or ``libedit``. ``libreadline`` is licensed under
GNU GPL Version 3, and ``libedit`` has a more permissive license.

``libedit``/``libreadline`` link against a curses library, most likely
``ncurses``. And ``ncurses`` has tie-ins with a terminal database. This
is a thorny situation, as terminal databases can be difficult to
distribute because end-users often want software to respect their
terminal databases. But for that to work, ``ncurses`` needs to be compiled
in a way that respects the user's environment.

On macOS, we use the system ``libedit`` and ``libncurses``, which is
typically provided in ``/usr/lib``.

On Linux, we build ``libedit`` and ``ncurses`` from source and statically
link against their respective libraries. Project releases before 2023 linked
against ``readline`` on Linux.

gettext / locale Module
-----------------------

The ``locale`` Python module exposes some functionality from the ``gettext``
software (specifically ``libintl``). (Technically, this functionality is exposed
from the ``_locale`` C extension module and ``locale`` re-exports symbols.)

``gettext`` is GPL version 3 or later licensed. And having it statically linked
in the Python distribution via the ``_locale`` module can have licensing
implications.

Python's configure script probes for the ability to compile/link with
``-lintl``. If it works, Python is linked against ``libintl``. If it doesn't,
``libintl`` is omitted. (Search ``configure`` for ``ac_cv_lib_intl_textdomain``
and ``-lintl`` references.)

With the container based build environment on Linux, presence of ``gettext``
and ``libintl`` is deterministic. However, on macOS where there is no
sandboxing of the build environment, Python's configure script can find and
use a ``gettext``/``libintl`` installed outside the system default (e.g. via
Homebrew or MacPorts). This can result in the built Python referencing a shared
library not reliably present on every macOS machine. So our build system
disables the configure check.

This means that the ``gettext``/``libintl`` features in the Python distribution
are not available.

libnsl / nis Module
-------------------

The ``nis`` Python extension module has a dependency on ``libnsl``.

``libnsl`` has historically been in base Linux distribution installations.
But it is being phased away, with it being an optional install in modern
versions of Fedora and RHEL.

Because the ``nis`` extension is perceived to be likely unused functionality,
we've decided to not build it instead of adding complexity to deal with
the ``libnsl`` dependency. See further discussion in
https://github.com/astral-sh/python-build-standalone/issues/51.

The ``nis`` module was deprecated in Python 3.11 and removed in 3.13.

Upgrading CPython
=================

This section documents some of the work that needs to be performed
when upgrading CPython major versions.

Review Release Notes
--------------------

CPython's release notes often have a section on build system changes.
e.g. https://docs.python.org/3/whatsnew/3.13.html#build-changes.
These are a must review.

``Modules/Setup``
-----------------

The ``Modules/Setup`` file defines the default extension build settings.

We need to audit it for differences such as added/removed extensions,
changes to compile settings, etc just in case we have special code
handling an extension defined in this file.

See code in ``cpython.py`` dealing with this file.
