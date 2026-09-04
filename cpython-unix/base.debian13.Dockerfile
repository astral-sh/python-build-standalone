# Debian Trixie.
FROM debian@sha256:fe7312b5f05bf5f43fad76bcd8945642e4e47a68aefd1b73f447615899d0fac1
LABEL org.opencontainers.image.authors="Jonathan J. Helmus<jjhelmus@gmail.com>"

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

RUN for suite in trixie trixie-updates; do \
      echo "deb http://snapshot.debian.org/archive/debian/20260624T024300Z/ ${suite} main"; \
    done > /etc/apt/sources.list && \
    echo "deb http://snapshot.debian.org/archive/debian-security/20260624T024300Z/ trixie-security main" >> /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/* && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable && \
    apt-get update
