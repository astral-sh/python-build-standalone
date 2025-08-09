# Debian Stretch.
FROM debian@sha256:c5c5200ff1e9c73ffbf188b4a67eb1c91531b644856b4aefe86a58d2f0cb05be
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

RUN for s in debian_stretch debian_stretch-updates debian-security_stretch/updates; do \
      echo "deb http://snapshot.debian.org/archive/${s%_*}/20230423T032736Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Check-Valid-Until "false";'; \
      echo 'Acquire::Retries "5";'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable

# apt iterates all available file descriptors up to rlim_max and calls
# fcntl(fd, F_SETFD, FD_CLOEXEC). This can result in millions of system calls
# (we've seen 1B in the wild) and cause operations to take seconds to minutes.
# Setting a fd limit mitigates.
#
# Attempts at enforcing the limit globally via /etc/security/limits.conf and
# /root/.bashrc were not successful. Possibly because container image builds
# don't perform a login or use a shell the way we expect.
RUN ulimit -n 10000 && apt-get update
