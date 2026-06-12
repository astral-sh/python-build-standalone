# Debian Stretch.
FROM debian@sha256:cebe6e1c30384958d471467e231f740e8f0fd92cbfd2a435a186e9bada3aee1c
LABEL org.opencontainers.image.authors="Gregory Szorc <gregory.szorc@gmail.com>"

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

# Stretch stopped publishing snapshots in April 2023. Last snapshot
# is 20230423T032533Z. But there are package authentication issues
# with this snapshot.
RUN for s in debian_stretch debian_stretch-updates debian-security_stretch/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20221105T150728Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable

RUN apt-get update

# Build tools, same as in build.Dockerfile
RUN apt-get install \
    bzip2 \
    ca-certificates \
    curl \
    file \
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

# Target sysroots and host binutils for cross-compiling with the external LLVM
# toolchain.
RUN apt-get install \
    binutils-arm-linux-gnueabi \
    binutils-arm-linux-gnueabihf \
    binutils-mips-linux-gnu \
    binutils-mipsel-linux-gnu \
    binutils-powerpc64le-linux-gnu \
    binutils-s390x-linux-gnu \
    libc6-armel-cross \
    libc6-armhf-cross \
    libc6-mips-cross \
    libc6-mipsel-cross \
    libc6-ppc64el-cross \
    libc6-s390x-cross \
    libc6-dev-armel-cross \
    libc6-dev-armhf-cross \
    libc6-dev-mips-cross \
    libc6-dev-mipsel-cross \
    libc6-dev-ppc64el-cross \
    libc6-dev-s390x-cross \
    linux-libc-dev-armel-cross \
    linux-libc-dev-armhf-cross \
    linux-libc-dev-mips-cross \
    linux-libc-dev-mipsel-cross \
    linux-libc-dev-ppc64el-cross \
    linux-libc-dev-s390x-cross \
    libgcc1-armel-cross \
    libgcc1-armhf-cross \
    libgcc1-mips-cross \
    libgcc1-mipsel-cross \
    libgcc1-ppc64el-cross \
    libgcc1-s390x-cross \
    libgcc-6-dev-armel-cross \
    libgcc-6-dev-armhf-cross \
    libgcc-6-dev-mips-cross \
    libgcc-6-dev-mipsel-cross \
    libgcc-6-dev-ppc64el-cross \
    libgcc-6-dev-s390x-cross

# Target-specific symlinks to cross-compile using the external LLVM toolchain.
RUN ln -s /tools/llvm/bin/clang /usr/bin/arm-linux-gnueabi-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/arm-linux-gnueabi-clang++ && \
    ln -s /tools/llvm/bin/clang /usr/bin/arm-linux-gnueabihf-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/arm-linux-gnueabihf-clang++ && \
    ln -s /tools/llvm/bin/clang /usr/bin/mips-linux-gnu-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/mips-linux-gnu-clang++ && \
    ln -s /tools/llvm/bin/clang /usr/bin/mipsel-linux-gnu-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/mipsel-linux-gnu-clang++ && \
    ln -s /tools/llvm/bin/clang /usr/bin/powerpc64le-linux-gnu-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/powerpc64le-linux-gnu-clang++ && \
    ln -s /tools/llvm/bin/clang /usr/bin/s390x-linux-gnu-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/s390x-linux-gnu-clang++
