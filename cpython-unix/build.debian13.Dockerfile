# Keep target headers, startup objects, and shared libraries on the same
# Debian Stretch snapshot previously used for the entire aarch64 build image.
{% include 'base.debian9.Dockerfile' %}

RUN ulimit -n 10000 && apt-get install libc6-dev-arm64-cross

# Build tools and host programs run against current Debian Trixie libraries.
{% include 'base.debian13.Dockerfile' %}

RUN apt-get install \
    bzip2 \
    ca-certificates \
    curl \
    file \
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

COPY --from=0 /usr/aarch64-linux-gnu/ /usr/aarch64-linux-gnu/

# Cross libc linker scripts contain absolute /usr/aarch64-linux-gnu/lib paths,
# which ld resolves relative to --sysroot. Mirror that prefix and the standard
# /usr/include and /usr/lib paths inside the otherwise flat cross sysroot.
RUN sysroot=/usr/aarch64-linux-gnu && \
    mkdir "${sysroot}/usr" && \
    ln -s .. "${sysroot}/usr/aarch64-linux-gnu" && \
    ln -s ../include "${sysroot}/usr/include" && \
    ln -s ../lib "${sysroot}/usr/lib"
