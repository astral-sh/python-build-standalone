{% include 'base.Dockerfile' %}

# libffi-dev and zlib1g-dev are present so host Python (during cross-builds)
# can build the ctypes and zlib extensions. So comment in build-cpython.sh
# for more context.
#
# Compression packages are needed to extract archives.
#
# Various other build tools are needed for various building.
# Note linux-headers is installed to source a missing UAPI header, see below
RUN ulimit -n 10000 && apt-get install \
    bzip2 \
    ca-certificates \
    curl \
    file \
    libc6-dev \
    linux-headers-3.16.0-6-common \
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

# Debian Jessie's linux-libc-dev is missing the vm_sockets header due to a typo
# see https://lists.openwall.net/netdev/2014/12/01/2
RUN install -m 0644 /usr/src/linux-headers-3.16.0-6-common/include/uapi/linux/vm_sockets.h \
    /usr/include/linux/vm_sockets.h