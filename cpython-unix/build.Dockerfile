{% include 'base.Dockerfile' %}

# libc6-dev:i386 pulls in 32-bit system libraries to enable cross-compiling
# to i386.
#
# libffi-dev and zlib1g-dev are present so host Python (during cross-builds)
# can build the ctypes and zlib extensions. So comment in build-cpython.sh
# for more context.
#
# Compression packages are needed to extract archives.
#
# Various other build tools are needed for various building.
RUN ulimit -n 10000 && apt-get install \
    bzip2 \
    file \
    libc6-dev \
    libc6-dev:i386 \
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
