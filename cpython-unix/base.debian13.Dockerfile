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

# The base image has no CA bundle. Download Debian's certificate package over
# HTTPS with BuildKit and verify it against the hash from the snapshot's signed
# package index. Use its certificates to bootstrap APT over HTTPS.
ADD --checksum=sha256:c10585ac22c7f617a73d394eea29ba71d0356f350ae973b19043d1b017f80f54 \
    https://snapshot.debian.org/archive/debian-security/20261023T000000Z/pool/updates/main/c/ca-certificates/ca-certificates_20250419+deb13u1_all.deb \
    /tmp/bootstrap-ca-certificates.deb

RUN dpkg-deb -x /tmp/bootstrap-ca-certificates.deb /tmp/bootstrap-ca && \
    cat /tmp/bootstrap-ca/usr/share/ca-certificates/mozilla/*.crt > /tmp/bootstrap-ca.pem && \
    rm -rf /tmp/bootstrap-ca /tmp/bootstrap-ca-certificates.deb && \
    for suite in trixie trixie-updates; do \
      echo "deb https://snapshot.debian.org/archive/debian/20261023T000000Z/ ${suite} main"; \
    done > /etc/apt/sources.list && \
    echo "deb https://snapshot.debian.org/archive/debian-security/20261023T000000Z/ trixie-security main" >> /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/* && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable && \
    apt-get -o Acquire::https::CAInfo=/tmp/bootstrap-ca.pem update && \
    apt-get -o Acquire::https::CAInfo=/tmp/bootstrap-ca.pem install ca-certificates && \
    rm /tmp/bootstrap-ca.pem
