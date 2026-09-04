# Debian Bookworm + GCC 14 from Trixie (GCC 14 supports -mcpu=power11).
FROM docker.io/library/debian@sha256:6bc30d909583f38600edd6609e29eb3fb284ab8affce8d0389f332fc91c2dd91
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

RUN printf '%s\n' \
      'deb https://deb.debian.org/debian bookworm main' \
      'deb https://deb.debian.org/debian bookworm-updates main' \
      'deb https://deb.debian.org/debian-security bookworm-security main' \
      'deb https://deb.debian.org/debian trixie main' \
    > /etc/apt/sources.list && \
    ( echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'APT::Default-Release "bookworm";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'Acquire::https::Verify-Peer "false";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable && \
    rm -f /etc/apt/sources.list.d/* && \
    apt-get update

# Host building (from bookworm).
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

# Cross-building: GCC 14 from Trixie supports -mcpu=power11; also upgrade binutils.
RUN apt-get install -t trixie \
    binutils-powerpc64le-linux-gnu \
    gcc-14-powerpc64le-linux-gnu \
    g++-14-powerpc64le-linux-gnu && \
    apt-get install \
    libc6-dev-ppc64el-cross
