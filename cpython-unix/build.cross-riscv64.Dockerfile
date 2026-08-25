# Debian Buster.
FROM debian@sha256:2a0c1b9175adf759420fe0fbd7f5b449038319171eb76554bb76cbe172b62b42
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

RUN for s in debian_buster debian_buster-updates debian-security_buster/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20250109T084424Z/ ${s#*_} main"; \
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

# riscv64 sysroot and host binutils for the riscv64-linux-gnu target
RUN apt-get install \
    binutils-riscv64-linux-gnu \
    libc6-riscv64-cross \
    libc6-dev-riscv64-cross \
    linux-libc-dev-riscv64-cross \
    libgcc1-riscv64-cross \
    libgcc-8-dev-riscv64-cross

# target specific symlinks to cross-compile using external LLVM toolchain
RUN ln -s /tools/llvm/bin/clang /usr/bin/riscv64-linux-gnu-clang && \
    ln -s /tools/llvm/bin/clang++ /usr/bin/riscv64-linux-gnu-clang++
