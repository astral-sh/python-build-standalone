# Debian Bookworm (ships GCC 12, which supports -mcpu=power10 and -mcpu=power11).
FROM debian@sha256:6bc30d909583f38600edd6609e29eb3fb284ab8affce8d0389f332fc91c2dd91
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

RUN for s in debian_bookworm debian_bookworm-updates debian-security_bookworm-security/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20250601T000000Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable && \
    rm -f /etc/apt/sources.list.d/*

RUN apt-get update

# Host building.
RUN apt-get install \
    bzip2 \
    ca-certificates \
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

# Cross-building (powerpc64le only — GCC 12 supports -mcpu=power10 and -mcpu=power11).
RUN apt-get install \
    g++-powerpc64le-linux-gnu \
    gcc-powerpc64le-linux-gnu \
    libc6-dev-ppc64el-cross
