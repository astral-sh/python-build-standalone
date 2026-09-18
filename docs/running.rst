.. _running:

=====================
Running Distributions
=====================

Using uv
========

The most common method of using the prebuilt distributions from this
project is with `uv <https://docs.astral.sh/uv/>`_. By default, uv will
download, install, and use an appropriate distribution if the system does
not provide a compatible Python installation that uv can discover. These
downloaded distributions are referred to as *managed* Python installations,
as compared to *system* Python installations. You can configure uv to
always use a *managed* Python installation, for example by using the
``--managed-python`` flag.

To run a particular distribution using ``uv``::

    uvx --managed-python python

A Python version or another specifier can be included::

    uvx --managed-python python@3.13
    uvx --managed-python python@3.14+freethreaded

The uv documentation on
`installing Python <https://docs.astral.sh/uv/guides/install-python/>`_
and `Python versions <https://docs.astral.sh/uv/concepts/python-versions/>`_
provides more information and examples.

Obtaining Distributions
=======================

Prebuilt distributions are published as releases on GitHub at
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
system the distribution runs on. We use LLVM target triples.
Distributions are produced for the following target triples:

``aarch64-apple-darwin``
   macOS ARM CPUs, i.e., Apple Silicon.

``x86_64-apple-darwin``
   macOS Intel CPUs.

``x86_64-pc-windows-msvc``
   Windows 64-bit Intel/AMD CPUs.

``i686-pc-windows-msvc``
   Windows 32-bit Intel/AMD CPUs.

``aarch64-pc-windows-msvc``
   Windows 64-bit ARM CPUs. Available for CPython 3.11 and newer.

``x86_64-unknown-linux-gnu``
   Linux 64-bit Intel/AMD CPUs linking against GNU libc.

``x86_64-unknown-linux-musl``
   Linux 64-bit Intel/AMD CPUs linking against musl libc.

   Distributions are provided that dynamically link musl or are fully static
   (``+static``). Dynamically linked distributions require musl to be installed
   on the host. Fully static distributions have no shared library dependencies,
   but cannot load Python ``.so`` extensions.

``aarch64-unknown-linux-*``
   Similar to above except targeting Linux on ARM64 CPUs. Distributions
   are provided for GNU libc, musl, and static musl.

   For example, this target supports AWS Graviton EC2 instances. Many
   Linux ARM devices are also ``aarch64``.

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

``armv7-unknown-linux-gnueabi``
   Linux 32-bit ARM CPUs without hardware floating-point instructions,
   linking against GNU libc.

   This is an uncommon platform. In most cases, the hardware floating-point
   target should be used. These distributions can be used on Debian's
   ``armel`` port.

``armv7-unknown-linux-gnueabihf``
   Linux 32-bit ARM CPUs with hardware floating-point instructions,
   linking against GNU libc.

   This is a common 32-bit ARM platform. Raspberry Pi model 2 and later
   can use these distributions on many 32-bit Linux distributions.

``ppc64le-unknown-linux-gnu``
   Linux 64-bit POWER8+ CPUs linking against GNU libc.

``riscv64-unknown-linux-gnu``
   Linux 64-bit RISC-V CPUs linking against GNU libc.

``s390x-unknown-linux-gnu``
   Linux 64-bit IBM Z (s390x) CPUs linking against GNU libc.

We recommend using the ``*-unknown-linux-gnu`` builds on Linux, since they
are able to load compiled Python extensions. The non-static
``*-unknown-linux-musl`` builds should be used on musl-based Linux
distributions like Alpine Linux. If you don't need to load compiled
extensions not provided by the standard library, or you are willing to
compile and link third-party extensions into a custom binary, the static
``*-unknown-linux-musl`` builds should work just fine.

The build configuration denotes how Python and its dependencies were built.
Common configurations include:

``pgo+lto``
   Profile-guided optimization and link-time optimization. **These should be
   the fastest distributions since they have the most build-time
   optimizations.**

``pgo``
   Profile-guided optimization.

   Starting with CPython 3.12, BOLT is also applied alongside traditional
   PGO on platforms supporting BOLT. (Currently just Linux x86-64.)

``lto``
   Link-time optimization.

``noopt``
   A regular optimized build without PGO or LTO.

``debug``
   A debug build. No optimizations.

``freethreaded``
   A free-threaded build, available for CPython 3.13 and newer. This
   option is combined with an optimization option, such as
   ``freethreaded+pgo+lto`` or ``freethreaded+lto``.

``static``
   A fully static musl build. Has no shared library dependencies and
   cannot load dynamically linked Python extensions.

The archive flavor denotes the content in the archive. See
:ref:`distributions` for more.

Casual users will likely want to use the ``install_only`` archive, as most
users do not need the build artifacts present in the ``full`` archive.
The ``install_only`` archive does not include the optimization options in
its filename. For each Python version, target, and threading variant,
it uses the fastest available build configuration.

An ``install_only_stripped`` archive is also available. This archive is
equivalent to ``install_only``, but without debug symbols, which results
in a smaller download and on-disk footprint. For CPython 3.13 and newer,
free-threaded archives are identified by ``freethreaded`` in the filename.

Fully static musl builds are only available as ``full`` archives with
``+static`` in their build options. The ``install_only`` and
``install_only_stripped`` musl archives use dynamically linked builds.

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

Distributions linked against glibc may reference the following shared
libraries:

* linux-vdso.so.1
* libpthread.so.0
* libdl.so.2 (required by ctypes extension)
* libutil.so.1
* librt.so.1
* libm.so.6
* libc.so.6
* ld-linux-x86-64.so.2

On Python 3.12 and earlier, the deprecated ``crypt`` module additionally
requires ``libcrypt.so.1``.

The minimum glibc version required for most targets is 2.17. This should make
binaries compatible with the following Linux distributions:

* Fedora 21+
* RHEL/CentOS 7+
* openSUSE 13.2+
* Debian 8+ (Jessie)
* Ubuntu 14.04+

For the ``riscv64-unknown-linux-gnu`` target, the minimum glibc version is
2.28.

Distributions linked against musl do not depend on glibc. By default, musl
distributions are dynamically linked and require musl to be installed on the
host. Fully static distributions use the ``+static`` build option and have
no shared library dependencies, but cannot load dynamically linked Python
extension modules.

Windows
-------

Windows distributions model the requirements of the official Python
distributions:

* CPython 3.14 and newer: Windows 10 or newer.
* CPython 3.13 and earlier: Windows 8.1 or newer.

Windows Server support follows the corresponding CPython release's
upstream platform policy.

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

The distributions that contain object files are useful for
embedding Python in a larger binary. See the
`PyOxidizer <https://github.com/indygreg/PyOxidizer>`_ sister project
for such a downstream repackager.

Some users of these distributions might be better served by the
`PyOxy <https://pyoxidizer.readthedocs.io/en/latest/pyoxy.html>`_
sister project. PyOxy takes these Python distributions and adds Rust code
to enhance the functionality of the Python interpreter. The official
PyOxy release binaries are single-file executables providing
a full-featured Python interpreter.
