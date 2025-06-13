# Debian Trixie.
FROM debian@sha256:653dfb9f86c3782e8369d5f7d29bb8faba1f4bff9025db46e807fa4c22903671
MAINTAINER Gregory Szorc <gregory.szorc@gmail.com>

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

RUN for s in debian_trixie debian_trixie-updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20250515T202920Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list && \
    for s in debian-security_trixie-security/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20250515T175729Z/ ${s#*_} main"; \
    done >> /etc/apt/sources.list && \
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
    curl \
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
    gcc-loongarch64-linux-gnu \
    libc6-dev-loong64-cross

RUN cd /tmp && \
    curl -LO https://snapshot.debian.org/archive/debian-ports/20250515T194251Z/pool-loong64/main/libx/libxcrypt/libcrypt-dev_4.4.38-1_loong64.deb && \
    curl -LO https://snapshot.debian.org/archive/debian-ports/20250515T194251Z/pool-loong64/main/libx/libxcrypt/libcrypt1_4.4.38-1_loong64.deb && \
    dpkg -x libcrypt-dev_4.4.38-1_loong64.deb / && \
    dpkg -x libcrypt1_4.4.38-1_loong64.deb / && \
    rm -f /tmp/*.deb
