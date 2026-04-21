# Debian Trixie
FROM debian@sha256:3352c2e13876c8a5c5873ef20870e1939e73cb9a3c1aeba5e3e72172a85ce9ed
LABEL org.opencontainers.image.authors="Jonathan J. Helmus <jjhelmus@gmail.com>"

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

# curl
RUN apt-get update && apt install --yes curl

# Add the LLVM project repository
RUN curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
        -o /etc/apt/trusted.gpg.d/apt.llvm.org.asc \
    && echo "deb http://apt.llvm.org/trixie/ llvm-toolchain-trixie-22 main" \
        > /etc/apt/sources.list.d/llvm.list

# Add buster as an source for riscv sysroot packages
RUN for s in debian_buster debian_buster-updates debian-security_buster/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20250109T084424Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list.d/buster.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable

# Pin the riscv sysroot packages to buster
RUN printf 'Package: *-riscv64-cross\nPin: release n=buster\nPin-Priority: 900\n' \
        > /etc/apt/preferences.d/buster-cross

RUN apt-get update

# Host building.
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

# LLVM
RUN apt-get install \
    clang-22 \
    lld-22 \
    llvm-22

RUN apt-get install \
    libc6-dev-riscv64-cross \
    libc6-riscv64-cross \
    linux-libc-dev-riscv64-cross \
    libgcc1-riscv64-cross \
    libgcc-8-dev-riscv64-cross

RUN ln -s /usr/bin/clang-22 /usr/bin/riscv64-linux-gnu-clang && \
    ln -s /usr/bin/clang++-22 /usr/bin/riscv64-linux-gnu-clang++ && \
    ln -s /usr/lib/llvm-22/bin/ld.lld /usr/bin/riscv64-linux-gnu-ld