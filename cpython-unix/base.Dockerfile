# Debian Jessie.
FROM debian@sha256:32ad5050caffb2c7e969dac873bce2c370015c2256ff984b70c1c08b3a2816a0
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

# Jessie's archive signing keys have expired. Authenticate the immutable package
# indexes with SHA-256 instead; APT checks each downloaded package against them.
# These images run on amd64, including the cross-compilation toolchains.
# Do not refresh these indexes with apt-get update: trusted=yes is safe only
# with the pinned indexes below. See docs/building.rst for the trust chain.
RUN rm -rf /var/lib/apt/lists/* && \
    for s in debian_jessie debian_jessie-updates debian-security_jessie/updates; do \
      echo "deb [trusted=yes] http://snapshot.debian.org/archive/${s%_*}/20230322T152120Z/ ${s#*_} main"; \
    done > /etc/apt/sources.list && \
    ( echo 'quiet "true";'; \
      echo 'APT::Get::Assume-Yes "true";'; \
      echo 'APT::Install-Recommends "false";'; \
      echo 'Acquire::Retries "5";'; \
      echo 'APT::Update::Pre-Invoke { "echo Jessie indexes are pinned in base.Dockerfile >&2; exit 1"; };'; \
    ) > /etc/apt/apt.conf.d/99cpython-portable

{% for repository, suite, sha256 in [
    ('debian', 'jessie', '7240a1c6ce11c3658d001261e77797818e610f7da6c2fb1f98a24fdbf4e8d84c'),
    ('debian', 'jessie-updates', 'f61f27bd17de546264aa58f40f3aafaac7021e0ef69c17f6b1b4cd7664a037ec'),
    ('debian-security', 'jessie/updates', '3da1205c671e38db711a76403b27f1b3e0b84766edcf717a4b9daea9d4c693b2'),
] %}
ADD --checksum=sha256:{{ sha256 }} \
    https://snapshot.debian.org/archive/{{ repository }}/20230322T152120Z/dists/{{ suite }}/main/binary-amd64/Packages.gz \
    /var/lib/apt/lists/snapshot.debian.org_archive_{{ repository }}_20230322T152120Z_dists_{{ suite | replace('/', '_') }}_main_binary-amd64_Packages.gz
{% endfor %}

# apt iterates all available file descriptors up to rlim_max and calls
# fcntl(fd, F_SETFD, FD_CLOEXEC). This can result in millions of system calls
# (we've seen 1B in the wild) and cause operations to take seconds to minutes.
# Setting a fd limit mitigates.
#
# Attempts at enforcing the limit globally via /etc/security/limits.conf and
# /root/.bashrc were not successful. Possibly because container image builds
# don't perform a login or use a shell the way we expect.
#
# The pinned base lacks HTTPS support. Bootstrap it using the authenticated
# package hashes, then use HTTPS for all subsequent package downloads.
RUN ulimit -n 10000 && \
    apt-get install apt-transport-https ca-certificates && \
    sed -i 's|http://snapshot.debian.org|https://snapshot.debian.org|' /etc/apt/sources.list
