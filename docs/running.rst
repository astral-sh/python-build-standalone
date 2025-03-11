.. _running:

=====================
Running Distributions
=====================

Obtaining Distributions
=======================

Pre-built distributions are published as releases on GitHub at
https://github.com/astral-sh/python-build-standalone/releases.
Simply go to that page and find the latest release along with
its release notes.

Machines can find the latest release by querying the GitHub releases
API. Alternatively, a JSON file publishing metadata about the latest
release can be fetched from
https://raw.githubusercontent.com/astral-sh/python-build-standalone/latest-release/latest-release.json.
The JSON format is simple and hopefully self-descriptive.

Published distributions vary by their:

* Python version
* Target machine architecture
* Build configuration
* Archive flavor

The Python version is hopefully pretty obvious.

The target machine architecture defines the CPU type and operating
system the distribution runs on. We use LLVM target triples. If you aren't
familiar with LLVM target triples, here is an overview:

``aarch64-apple-darwin``
   macOS ARM CPUs. i.e. M1 native binaries.

``x86_64-apple-darwin``
   macOS Intel CPUs.

``i686-pc-windows-msvc``
   Windows 32-bit Intel/AMD CPUs.

``x86_64-pc-windows-msvc``
   Windows 64-bit Intel/AMD CPUs.

``*-windows-msvc-shared``
   This is a standard build of Python for Windows. There are DLLs for
   Python and extensions. These builds behave like the official Python
   for Windows distributions.

   These builds are now published without the `-shared` suffix.

``*-windows-msvc-static``
   These builds of Python are statically linked.

   These builds are extremely brittle and have several known incompatibilities.
   We recommend not using them unless you have comprehensive test coverage and
   have confidence they work for your use case.

   See :ref:`quirk_windows_static_distributions` for more.

   These builds are no longer published.

``x86_64-unknown-linux-gnu``
   Linux 64-bit Intel/AMD CPUs linking against GNU libc.

``x86_64-unknown-linux-musl``
   Linux 64-bit Intel/AMD CPUs linking against musl libc.

   These binaries are static and have no shared library dependencies.
   A side-effect of static binaries is they cannot load Python ``.so``
   extensions, as static binaries cannot load shared libraries.

``aarch64-unknown-linux-*``
   Similar to above except targeting Linux on ARM64 CPUs.

   This is what you want for e.g. AWS Graviton EC2 instances. Many Linux
   ARM devices are also ``aarch64``.

``i686-unknown-linux-*``
   Linux 32-bit Intel/AMD CPUs.

``x86_64_v2-*``
   Targets 64-bit Intel/AMD CPUs approximately newer than
   `Nehalem <https://en.wikipedia.org/wiki/Nehalem_(microarchitecture)>`_
   (released in 2008).

   Binaries will have SSE3, SSE4, and other CPU instructions added after the
   ~initial x86-64 CPUs were launched in 2003.

   Binaries will crash if you attempt to run them on an older CPU not
   supporting the newer instructions.

``x86_64_v3-*``
   Targets 64-bit Intel/AMD CPUs approximately newer than
   `Haswell <https://en.wikipedia.org/wiki/Haswell_(microarchitecture)>`_
   (released in 2013) and
   `Excavator <https://en.wikipedia.org/wiki/Excavator_(microarchitecture)>`_
   (released in 2015).

   Binaries will have AVX, AVX2, MOVBE and other newer CPU instructions.

   Binaries will crash if you attempt to run them on an older CPU not
   supporting the newer instructions.

   Most x86-64 CPUs manufactured after 2013 (Intel) or 2015 (AMD) support
   this microarchitecture level. An exception is Intel Atom P processors,
   which Intel released in 2020 but did not include AVX.

``x86_64_v4-*``
   Targets 64-bit Intel/AMD CPUs with some AVX-512 instructions.

   Requires Intel CPUs manufactured after ~2017. But many Intel CPUs don't
   have AVX-512.

The ``x86_64_v2``, ``x86_64_v3``, and ``x86_64_v4`` binaries usually crash
on startup when run on an incompatible CPU. We don't recommend running the
``x86_64_v4`` builds in production because they likely don't yield a reliable
performance benefit. Unless you are executing these binaries on a CPU older
than ~2008 or ~2013, we recommend running the ``x86_64_v2`` or ``x86_64_v3``
binaries, as these should be slightly faster since they take advantage
of more modern CPU instructions which are more efficient. But if you want
maximum portability, stick with the baseline ``x86_64`` builds.

We recommend using the ``*-windows-msvc-shared`` builds on Windows, as these
are highly compatible with the official Python distributions.

We recommend using the ``*-unknown-linux-gnu`` builds on Linux, since they
are able to load compiled Python extensions. If you don't need to load
compiled extensions not provided by the standard library or you are willing
to compile and link 3rd party extensions into a custom binary, the
``*-unknown-linux-musl`` builds should work just fine.

The build configuration denotes how Python and its dependencies were built.
Common configurations include:

``pgo+lto``
   Profile guided optimization and link-time optimization. **These should be
   the fastest distributions since they have the most build-time
   optimizations.**

``pgo``
   Profile guided optimization.

   Starting with CPython 3.12, BOLT is also applied alongside traditional
   PGO on platforms supporting BOLT. (Currently just Linux x86-64.)

``lto``
   Link-time optimization.

``noopt``
   A regular optimized build without PGO or LTO.

``debug``
   A debug build. No optimizations.

The archive flavor denotes the content in the archive. See
:ref:`distributions` for more.

Casual users will likely want to use the ``install_only`` archive, as most
users do not need the build artifacts present in the ``full`` archive.
The ``install_only`` archive doesn't include the build configuration in its
file name. It's based on the fastest available build configuration for a given
target.

An ``install_only_stripped`` archive is also available. This archive is
equivalent to ``install_only``, but without debug symbols, which results in a
smaller download and on-disk footprint.

Extracting Distributions
========================

Distributions are defined as zstandard or gzip compressed tarballs.

Modern versions of ``tar`` support zstandard and you can extract
like any normal archive::

   $ tar -axvf path/to/distribution.tar.zstd

(The ``-a`` argument tells tar to guess the compression format by
the file extension.)

If your ``tar`` doesn't support ``-a`` (e.g. the default macOS ``tar``),
try::

   $ tar xvf path/to/distribution.tar.zstd

If you do not have ``tar``, you can install and use the ``zstd``
tool (typically available via a ``zstd`` or ``zstandard`` system
package)::

   $ zstd -d path/to/distribution.tar.zstd
   $ tar -xvf path/to/distribution.tar

If you want to extract the distribution with Python, use the
``zstandard`` Python package:

.. code-block:: python

   import tarfile
   import zstandard

   with open("path/to/distribution.tar.zstd", "rb") as ifh:
       dctx = zstandard.ZstdDecompressor()
       with dctx.stream_reader(ifh) as reader:
           with tarfile.open(mode="r|", fileobj=reader) as tf:
               tf.extractall("path/to/output/directory")

Runtime Requirements
====================

Linux
-----

The produced Linux binaries have minimal references to shared
libraries and thus can be executed on most Linux systems.

The following shared libraries are referenced:

* linux-vdso.so.1
* libpthread.so.0
* libdl.so.2 (required by ctypes extension)
* libutil.so.1
* librt.so.1
* libcrypt.so.1 (required by crypt extension)
* libm.so.6
* libc.so.6
* ld-linux-x86-64.so.2

The minimum glibc version required for most targets is 2.17. This should make
binaries compatible with the following Linux distributions:

* Fedora 21+
* RHEL/CentOS 7+
* openSUSE 13.2+
* Debian 8+ (Jessie)
* Ubuntu 14.04+

For the ``mips-unknown-linux-gnu`` and ``mipsel-unknown-linux-gnu`` targets,
the minimum glibc version is 2.19.

If built with MUSL, no shared library dependencies nor glibc version
requirements exist and the binaries should *just work* on practically any
Linux system.

Windows
-------

Windows distributions model the requirements of the official Python
distributions:

* Windows 8 or Windows Server 2012 or newer

Windows binaries have a dependency on the Microsoft Visual C++ Redistributable,
likely from MSVC 2015 (``vcruntime140.dll``). This dependency is not
provided in the distribution and will need to be provided by downstream
distributors.

Extra Python Software
=====================

Python installations have some additional software pre-installed:

* `pip <https://pypi.org/project/pip/>`_
* `setuptools <https://pypi.org/project/setuptools/>`_ (for Python 3.11 and older)

The intent of the pre-installed software is to facilitate end-user
package installation without having to first bootstrap a packaging
tool via an insecure installation technique (such as `curl | sh`
patterns).

Licensing
=========

Python and its various dependencies are governed by varied software use
licenses. This impacts the rights and requirements of downstream consumers.

Most licenses are fairly permissive. Notable exceptions to this are GDBM and
readline, which are both licensed under GPL Version 3.

We build CPython against libedit - as opposed to readline - to avoid this
GPL dependency. This requires patches on CPython < 3.10. Distribution releases
before 2023 may link against readline and are therefore subject to the GPL.

We globally disable the ``_gdbm`` extension module to avoid linking against
GDBM and introducing a GPL dependency. Distribution releases before 2023 may
link against GDBM and be subject to the GPL.

**It is important to understand the licensing requirements when integrating
the output of this project into derived works.** To help with this, the
JSON document describing the Python distribution contains licensing metadata
and the archive contains copies of license texts.

Reconsuming Build Artifacts
===========================

Produced Python distributions contain object files and libraries for the
built Python and its dependencies. It is possible for downstream consumers
to take these build artifacts and link them into a new binary.

Reconsuming the build artifacts this way can be a bit fragile due to
incompatibilities between the host that generated them and the target that
is consuming them.

To ensure optimal compatibility, it is highly recommended to use the same
toolchain for all operations.

This is often harder than it sounds. For example, if these build artifacts
were to be combined into a Rust binary, the version of LLVM that the Rust
compiler itself was built against can matter. As a concrete example, the
Rust 1.31 compiler will produce LLVM intrinsics that vary from intrinsics
that would be produced with LLVM/Clang 7. At linking time, you would get
errors like the following::

    Intrinsic has incorrect argument type!
    void (i8*, i8, i64, i1)* @llvm.memset.p0i8.i64

In the future, we will allow configuring the toolchain used so it can match
requirements of downstream consumers. For the moment, we hard-code the toolchain
version.
