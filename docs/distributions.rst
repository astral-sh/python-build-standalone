.. _distributions:

=====================
Distribution Archives
=====================

This project produces tarball archives containing Python distributions.

Full Archive
============

The canonical output of this project's build system are ``.tar.zst``
(zstandard compressed tarballs) files.

All files within the tar are prefixed with ``python/``.

Within the ``python/`` directory are the following well-known paths:

PYTHON.json
   Machine readable file describing this Python distribution.

   See the ``PYTHON.json File`` section for the format of this file.

By convention, the ``build/`` directory contains artifacts from building
this distribution (object files, libraries, etc) and the ``install/`` directory
contains a working, self-contained Python installation of this distribution.
The ``PYTHON.json`` file should be read to determine where specific entities
are located within the archive.

PYTHON.json File
----------------

The ``PYTHON.json`` file describes the Python distribution in a machine
readable manner. This file is meant to be opened by downstream consumers
of this distribution so that they may learn things about the distribution
without having to resort to heuristics.

The file contains a JSON map. This map has the following keys:

version
   Version number of the file format. Currently ``8``.

target_triple
   A target triple defining the platform and architecture of the machine
   that binaries target. We use Rust's set of defined targets for values.
   Run ``rustup target list`` to see potential values.

   Example values are ``x86_64-unknown-linux-gnu``,
   ``x86_64-unknown-linux-musl``, ``x86_64-pc-windows-msvc``,
   and ``x86_64-apple-darwin``.

   (Version 5 or above only.)

optimizations
   String indicating what optimization profile has been applied to the
   build.

   Known values include ``debug``, ``noopt``, ``pgo``, ``lto``, and
   ``pgo+lto``.

   (Deprecated in version 8 in favor of ``build_options``.)

build_options
   String indicating what build options were used. Options are separated
   by a ``+``.

   Known values include ``debug``, ``noopt``, ``pgo``, ``lto``, and
   ``freethreading``.

   (Version 8 or above only.)

os
   Target operating system for the distribution. e.g. ``linux``, ``macos``,
   or ``windows``.

   (Deprecated in version 5 in favor of ``target_triple``.)

arch
   Target architecture for the distribution. e.g. ``x86`` (32-bit) or
   ``x86_64`` (64-bit).

   (Deprecated in version 5 in favor of ``target_triple``.)

python_tag
   The PEP 425 *Python Tag* value. e.g. ``cp313``.

   (Version 5 or above only.)

python_abi_tag
   The PEP 425 *ABI Tag* value. e.g. ``cp313m``.

   This may be null if the distribution's platform doesn't expose the concept
   of an ABI tag.

   (Version 5 or above only.)

python_platform_tag
   The PEP 425 *Platform Tag* value. e.g. ``linux_x86_64``.

   (Version 5 or above only.)

python_flavor
   Type of Python distribution. e.g. ``cpython``.

   (Deprecated in version 5 in favor of PEP 425 tags.)

python_implementation_cache_tag
   Tag used by import machinery to derive filenames for bytecode files.

   This is the value exposed by ``sys.implementation.cache_tag``

   (Version 5 or above only.)

python_implementation_hex_version
   Hexidecimal expression of implementation version.

   This is the value exposed by ``sys.implementation.hexversion``.

   (Version 5 or above only.)

python_implementation_name
   Name of Python implementation.

   This is the value exposed by ``sys.implementation.name``.

   (Version 5 or above only.)

python_implementation_version
   Array of version components of Python implementation.

   This is the value exposed by ``sys.implementation.version``.

   Unlike ``sys.implementation.version``, all elements are strings,
   not a mix of numbers and strings.

   (Version 5 or above only.)

python_version
   Version of Python distribution. e.g. ``3.13.0``.

python_major_minor_version
   ``X.Y`` version string consisting of Python major and minor version.

   (Version 5 or above only.)

python_paths
   Mapping of ``sysconfig`` path names to paths in the distribution.

   Keys are values like ``stdlib`` and ``include``. Values are relative
   paths within the distribution.

   See https://docs.python.org/3/library/sysconfig.html#installation-paths
   for the meaning of keys.

   (Version 5 or above only.)

python_paths_abstract
   Mapping of ``sysconfig`` path names with placeholder values.

   See https://docs.python.org/3/library/sysconfig.html#installation-paths
   for the meaning of keys.

   This is equivalent to calling ``sysconfig.get_paths(expand=False)``.

   (Version 6 or above only.)

python_config_vars
   Mapping of string configuration names to string values.

   This is equivalent to ``sysconfig.get_config_vars()`` with all values
   normalized to strings.

   Many configuration values may represent state as it existed in the
   build environment and aren't appropriate for the run-time environment
   on a different system.

   (Version 6 or above only.)

python_exe
   Relative path to main Python interpreter executable.

python_include
   Relative path to include path for Python headers. If this path is on
   the compiler's include path, ``#include <Python.h>`` should work.

   (Deprecated in version 5 in favor of ``python_paths``.)

python_stdlib
   Relative path to Python's standard library (where ``.py`` and resource
   files are located).

   (Deprecated in version 5 in favor of ``python_paths``.)

python_stdlib_platform_config
   Relative path to a ``config-<platform>`` directory in the standard
   library containing files used to embed Python in a binary.

   This is a standard directory present in POSIX Python installations
   and is not specific to this project.

   The key may be absent if no platform config directory exists.

   (Version 5 or above only.)

python_stdlib_test_packages
   Array of strings of Python packages that define tests. (Version 4 or above
   only.)

python_suffixes
   A map defining file suffixes for various Python file types. Each entry
   in the map is an array of strings.

   The map has the following keys.

   ``bytecode``
      Suffixes for bytecode modules. Corresponds to
      ``importlib.machinery.BYTECODE_SUFFIXES``. e.g. ``[".pyc"]``.

   ``debug_bytecode``
      Suffixes for debug bytecode modules. Corresponds to
      ``importlib.machinery.DEBUG_BYTECODE_SUFFIXES``. e.g. ``[".pyc"]``.

   ``extension``
      Suffixes for extension modules. Corresponds to
      ``importlib.machinery.EXTENSION_SUFFIXES``. e.g.
      ``[".cpython-313-x86_64-linux-gnu.so", ".abi3.so", ".so"]``.

   ``optimized_bytecode``
      Suffixes for optimized bytecode modules. Corresponds to
      ``importlib.machinery.OPTIMIZED_BYTECODE_SUFFIXES``. e.g.
      ``[".pyc"]``.

   ``source``
      Suffixes for source modules. Corresponds to
      ``importlib.machinery.SOURCE_SUFFIXES``. e.g. ``[".py"]``.

   (Version 5 or above only.)

python_bytecode_magic_number
   Magic number to use for bytecode files, expressed as a hexidecimal
   string.

   (Version 5 or above only.)

libpython_link_mode
   How `libpython` is linked. Values can be one of the following:

   `static`
      Statically linked.

   `shared`
      Dynamically linked. (A `libpythonXY` shared library will be part
      of the distribution.)

   (Version 5 or above only.)

link_mode
   Alias of ``libpython_link_mode``.

   (Version 4 or above only. Deprecated in version 5.)

python_symbol_visibility
   Defines how Python symbols are defined in binaries.

   ``global-default``
      (UNIX only.) Symbols are defined as *global* and have *default*
      binding, making them visible outside their defining component.

   ``dllexport``
      (Windows only.) Symbols are exported via ``__declspec(dllexport)``,
      making them visible to external libraries.

   (Version 5 or above only.)

python_extension_module_loading
   Defines support for loading Python extension modules.

   The value is an array of strings denoting support for various
   loading mechanisms.

   Note that downstream consumers reconstructing a new binary from
   object files or a static library can alter support depending on
   how that binary is linked.

   The special values are as follows.

   ``builtin``
       Supports loading of *builtin* extension modules compiled into
       the binary. (This should always be present.)

   ``shared-library``
       Supports loading of extension modules defined as shared
       libraries. e.g. from ``.so`` or ``.pyd`` files.

   (Version 5 or above only.)

apple_sdk_canonical_name
   Optional canonical name of Apple SDK used to build.

   Should only be present for target triples with ``apple`` in them.

   The canonical name can be used to find a copy of this SDK on another
   machine.

   (Version 7 or above only.)

apple_sdk_platform
   Optional name of the platform of the Apple SDK used to build.

   Should only be present for target triples with ``apple`` in them.

   e.g. ``macosx``

   (Version 7 or above only.)

apple_sdk_version
   Optional version of the Apple SDK used to build.

   Should only be present for target triples with ``apple`` in them.

   If relinking build artifacts, ideally this exact SDK version is used.
   Newer versions will likely work. Older versions or Clang toolchains
   associated with older versions may not.

   (Version 7 or above only.)

apple_sdk_deployment_target
   Optional version of the Apple SDK deployment target used to build.

   This effectively establishes a minimum version of the target operating
   system this binary is purportedly compatible with.

   (Version 7 or above only.)

crt_features
   Describes C Runtime features/requirements for binaries.

   The value is an array of strings denoting various properties.

   The special string values are as follows.

   ``glibc-dynamic``
      Binaries link dynamically against glibc.

   ``glibc-max-symbol-version:N``
      Denotes the max symbol version seen in glibc versioned symbols.

      This effectively advertises the oldest version of glibc that
      binaries support and indirectly advertises the oldest Linux
      distributions binaries can run on.

   ``static``
      Binaries link the CRT statically.

   ``vcruntime:N``
      Binaries link against the Microsoft Visual C++ Redistributable Runtime,
      version ``N``. ``N`` is a string like ``140``, which denotes the
      version component in a ``vcruntimeXYZ.dll`` file.

   ``libSystem``
      Binaries link against ``libSystem.B.dylib``, which is the mega
      library backing a lot of systems-level functionality in macOS.

   (Version 5 or above only.)

run_tests
   The path to a Python script to run the test harness for this
   distribution.

   (Version 5 or above only.)

build_info
   A map describing build configuration and artifacts for this distribution.

   See the ``build_info Data`` section below.

licenses
   Array of strings containing the license shortname identifiers from the
   SPDX license list (https://spdx.org/licenses/) for the Python distribution.

  (Version 2 or above only.)

license_path
   Path to a text file containing the license for this Python distribution.

   (Version 2 or above only.)

tcl_library_path
   Relative path to location of tcl library files. The path should be a
   directory tree containing tcl files to support the tkinter extension.
   This will include a subset of the library files provided by the tcl
   and tk packages.

   This points to the root directory containing tcl resources. Actual
   tcl resources are in sub-directories underneath, as identified by
   ``tcl_library_paths``.

   (Version 3 or above only.)

tcl_library_paths
   Array of relative paths holding tcl library files relative to
   ``tcl_library_path``.

   Because ``tcl_library_path`` can be shared with other resources
   (e.g. on UNIX the path is typically ``install/lib``, which holds
   system libraries as well), distributions may advertise the list
   of directories under ``tcl_library_path`` actually containing
   tcl resources.

   (Version 5 or above only.)

build_info Data
---------------

The ``build_info`` key in the ``PYTHON.json`` file describes build artifacts
in the Python distribution. The primary goal of the data is to give downstream
distribution consumers enough details to integrate build artifacts into their
own build systems. This includes the ability to produce a Python binary with a
custom set of built-in extension modules.

This map has the following keys:

core
   A map describing the core Python distribution (essentially `libpython`).

   objs
      An array of paths to object files constituting the Python core distribution.

      Core object files are typically object files that are linked together to
      create libpython.

   links
      An array of linking requirement maps. (See below for data format.)

   shared_lib
      Path to a shared library representing `libpython`. May not be defined.
      (Version 4 or above only.)

   static_lib
      Path to a static library representing `libpython`. May not be defined.
      (Version 4 or above only.)

   inittab_object
      Path to object file defining ``_PyImport_Inittab``, which defines
      built-in extension modules.

      (Version 5 or above only.)

   inittab_source
      Path to source code file that defines ``_PyImport_Inittab``. On
      CPython, this will point to a ``config.c`` file.

      (Version 5 or above only.)

   inittab_cflags
      Array of strings constituting compiler flags to use when compiling
      ``inittab_source``.

      (Version 5 or above only.)

extensions
   A map of extension names to an array of maps describing candidate extensions.

   Extensions are non-core/non-essential parts of the Python distribution that
   are frequently built as standalone entities.

   Names in this map denote the name of the extension module.

   Values are arrays of maps. Each map represents a potential candidate
   providing the extension. There is frequently only a single extension
   candidate. Multiple candidates can occur if there are e.g. varying
   libraries an extension can be linked against to supply underlying
   functionality.

   Each map has the following keys:

   in_core
      Boolean indicating if this extension is defined by the core distribution.

      If true, object files should be in the ``['core']['objs']`` array, not the
      ``objs`` array in this map.

      Downstream consumers should key off this value to determine how to
      assemble this extension's code into a new distribution.

      This field was introduced to support Windows, where CPython's Visual
      Studio project files define various extensions as part of the project
      providing libpython. This is in contrast to make-based builds, where
      the ``Modules/Setup.*`` files treat each extension as separate entities.

   init_fn
      The name of the extension module initialization function for this
      extension.

      The string value may be ``NULL``, which may need special handling by
      consumers.

   licenses
      Array of strings containing the license shortname identifiers from the
      SPDX license list (https://spdx.org/licenses/).

      If this field is missing, licenses are unknown. Empty array denotes no known
      licenses.

      The license applies to additional libraries needed by this extension, not
      the extension itself, as extensions should be licensed the same as the
      Python distribution.

      (Version 2 or above only.)

   license_path
      Paths to text files containing the licenses for this extension.

      (Version 2 or above only.)

   license_public_domain
      Bool indicating that the license for the extension is in the public
      domain.

      There is no SPDX identifier for public domain. And we want to be explicit
      about something being in the public domain because of the legal implications.

      (Version 2 or above only.)

   links
      An array of linking requirement maps. (See below for data format.)

   objs
      An array of paths to object files constituting this extension module.

   required
      Boolean indicating if this extension is required to initialize the Python
      interpreter.

   shared_lib
      The path to a shared library defining this extension module. May not
      be defined. (Version 4 or above only.)

   static_lib
      The path to a static library defining this extension module. May not
      be defined.

   variant
      String describing this extension variant. Downstream consumers can key off
      this value to choose an appropriate extension variant when there are
      multiple options.

object_file_format
   Denotes the data format for object files. Can be one of the following
   values.

   ``elf``
       Standard object file format for Linux.

   ``llvm-bitcode:N``
       Files are LLVM bitcode produced with LLVM version ``N``. e.g.
       ``llvm-bitcode:10.0.0``.

       This variant is typically seen for builds using LTO.

   ``coff``
       Standard object file format for Windows.

   ``mach-o``
       Standard object file format for macOS.

   (Version 5 or newer only.)

Each entry in a ``links`` array is a map with the following keys:

name
   Name of the library being linked against.

path_static
   Path to the static version of this library, if available in the
   distribution.

path_dynamic
   Path to the dynamic version of this library, if available in the
   distribution.

framework
   Denotes that the link target is a macOS framework.

system
   Denotes that the link target is a system library.

   System libraries are typically passed into the linker by name only and
   found using default library search paths.

Install Only Archive
====================

At release time, this project produces tar files containing just the
Python installation, without the ``PYTHON.json`` or build files from
the full ``.tar.zst`` archives. These are referred to as *install only*
archives.

An *install only* archive is created by taking a ``.tar.zst`` and
rewriting ``python/install/*`` to ``python/*``. All files not under
``python/install/*`` are not carried forward to the *install only*
archive.

The fastest available build for a given target is used for the *install
only* archive. Builds are generally preferred in the following order:
``pgo+lto``, ``pgo``, ``lto``, ``noopt``.

For maximum compatibility, gzipped compressed versions of the
*install only* archives are made available.
