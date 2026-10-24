{% include 'base.debian13.Dockerfile' %}

RUN apt-get install --yes ca-certificates

# Add buster as a source for riscv sysroot packages
RUN for s in debian_buster debian_buster-updates debian-security_buster/updates; do \
      echo "deb https://snapshot.debian.org/archive/${s%_*}/20250109T084424Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list.d/buster.list

# Pin the riscv sysroot packages to buster
RUN printf 'Package: *-riscv64-cross\nPin: release n=buster\nPin-Priority: 900\n' \
        > /etc/apt/preferences.d/buster-cross

RUN apt-get update

# Host building.
RUN apt-get install \
    bzip2 \
    gcc \
    g++ \
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

RUN apt-get install \
    libc6-dev-riscv64-cross \
    libc6-riscv64-cross \
    linux-libc-dev-riscv64-cross \
    libgcc1-riscv64-cross \
    libgcc-8-dev-riscv64-cross

# Debian's libc linker script uses paths rooted at /usr/riscv64-linux-gnu.
# Make them relative to the sysroot so LLD doesn't prepend the sysroot twice.
RUN sed -i 's@/usr/riscv64-linux-gnu/lib/@/lib/@g' /usr/riscv64-linux-gnu/lib/libc.so
