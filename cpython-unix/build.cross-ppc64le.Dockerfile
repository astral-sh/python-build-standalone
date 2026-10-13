# Debian Trixie + LLVM 23 + Debian Stretch ppc64el sysroot.
# LLVM 23 is used as a single consistent cross-compiler for all ppc64le
# variants (power9/power10/power11), avoiding the need for multiple GCC
# versions. The Stretch sysroot (glibc 2.24) matches the sysroot used by
# the existing ppc64le-unknown-linux-gnu target, ensuring the same glibc
# 2.17 runtime minimum across all ppc64le variants.
FROM debian@sha256:3352c2e13876c8a5c5873ef20870e1939e73cb9a3c1aeba5e3e72172a85ce9ed
LABEL org.opencontainers.image.authors="Veenious Geevarghese <veenious.geevarghese@ibm.com>"

RUN groupadd -g 1000 build && \
    useradd -u 1000 -g 1000 -d /build -s /bin/bash -m build && \
    mkdir /tools && \
    chown -R build:build /build /tools

ENV HOME=/build \
    SHELL=/bin/bash \
    USER=build \
    LOGNAME=build \
    HOSTNAME=builder \
    DEBIAN_FRONTEND=noninteractive

CMD ["/bin/bash", "--login"]
WORKDIR '/build'

# Port 80 is blocked in this build environment. Bootstrap over HTTPS with
# cert verification disabled just for the initial ca-certificates install,
# then re-enable for all subsequent steps.
RUN ( sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
      sed -i 's|http://deb.debian.org|https://deb.debian.org|g' \
        /etc/apt/sources.list ) && \
    apt-get -o Acquire::https::Verify-Peer=false update && \
    apt-get -o Acquire::https::Verify-Peer=false install --yes ca-certificates curl

# Add the LLVM 23 repository.
RUN curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
        -o /etc/apt/trusted.gpg.d/apt.llvm.org.asc \
    && echo "deb https://apt.llvm.org/trixie/ llvm-toolchain-trixie-23 main" \
        > /etc/apt/sources.list.d/llvm.list

# Add Debian Stretch as a source for ppc64el cross-libc packages.
# Stretch ships glibc 2.24; combined with the configure suppressions in
# build-cpython.sh this keeps the runtime minimum at glibc 2.17 —
# matching the existing ppc64le-unknown-linux-gnu target and x86 variants.
# Stretch stopped publishing snapshots in April 2023; last usable snapshot
# is 20221105T150728Z. Packages have auth issues so we mark trusted.
RUN for s in debian_stretch debian_stretch-updates debian-security_stretch/updates; do \
      echo "deb [trusted=yes] https://snapshot.debian.org/archive/${s%_*}/20221105T150728Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list.d/stretch.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable

# Pin the ppc64el sysroot packages to Stretch so they are not superseded
# by newer Trixie versions of the same package names.
RUN printf 'Package: *-ppc64el-cross\nPin: release n=stretch\nPin-Priority: 900\n' \
        > /etc/apt/preferences.d/stretch-cross

RUN apt-get update

# Host build tools.
RUN apt-get install \
    bzip2 \
    libc6-dev \
    libffi-dev \
    make \
    patch \
    perl \
    pkg-config \
    tar \
    xz-utils \
    unzip \
    zip \
    zlib1g-dev

# LLVM 23 — single compiler for all ppc64le variants.
# clang supports -mcpu=pwr9/pwr10/pwr11 natively; no separate GCC needed.
RUN apt-get install \
    clang-23 \
    lld-23 \
    llvm-23

# Stretch ppc64el cross-libc — provides the sysroot at /usr/powerpc64le-linux-gnu/.
# gcc-6-dev-ppc64el-cross provides the GCC 6 startup objects (crt*.o) that
# clang needs for the --gcc-install-dir flag.
RUN apt-get install \
    libc6-dev-ppc64el-cross \
    libc6-ppc64el-cross \
    linux-libc-dev-ppc64el-cross \
    libgcc1-ppc64el-cross \
    libgcc-6-dev-ppc64el-cross

# Cross libc linker scripts use absolute /usr/powerpc64le-linux-gnu/lib paths,
# which the linker resolves relative to --sysroot. Mirror that prefix and
# provide the standard include/library directories in the flat cross sysroot.
RUN sysroot=/usr/powerpc64le-linux-gnu && \
    mkdir "${sysroot}/usr" && \
    ln -s .. "${sysroot}/usr/powerpc64le-linux-gnu" && \
    ln -s ../include "${sysroot}/usr/include" && \
    ln -s ../lib "${sysroot}/usr/lib"

# CPython's configure searches for a target-prefixed archiver when cross-building.
RUN ln -s /usr/lib/llvm-23/bin/llvm-ar /usr/bin/powerpc64le-unknown-linux-gnu-llvm-ar

# build-cpython.sh prepends /tools/llvm/bin to PATH and invokes llvm-profdata,
# ld.lld, etc. from there. Satisfy those lookups with the apt-installed LLVM 23
# binaries so the build does not need a downloaded LLVM tarball.
RUN mkdir -p /tools/llvm/bin && \
    for b in clang-23 clang++-23 lld-23 llvm-ar llvm-profdata llvm-objcopy; do \
        src=$(command -v "$b" 2>/dev/null || echo "/usr/lib/llvm-23/bin/$b"); \
        ln -sf "$src" "/tools/llvm/bin/$b"; \
    done && \
    ln -sf /usr/lib/llvm-23/bin/lld /tools/llvm/bin/ld.lld && \
    ln -sf /usr/lib/llvm-23/bin/lld /tools/llvm/bin/lld && \
    ln -sf /usr/lib/llvm-23/bin/clang-23 /tools/llvm/bin/clang && \
    ln -sf /usr/lib/llvm-23/bin/clang++-23 /tools/llvm/bin/clang++
