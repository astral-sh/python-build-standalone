{% include 'base.debian13.Dockerfile' %}

# Host building.
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

# Keep the LoongArch glibc 2.39 sysroot from when Trixie was still testing.
RUN echo 'deb https://snapshot.debian.org/archive/debian/20240812T212427Z/ trixie main' \
        > /etc/apt/sources.list.d/loong64.list && \
    printf 'Package: *-loong64-cross gcc-14-cross-base-ports\nPin: release a=testing,n=trixie\nPin-Priority: 900\n' \
        > /etc/apt/preferences.d/loong64-cross && \
    apt-get -o APT::Update::Error-Mode=any update

# Clang and LLD need the target headers, libc and GCC startup/runtime objects.
RUN apt-get install \
    libc6-dev-loong64-cross \
    libgcc-14-dev-loong64-cross \
    linux-libc-dev-loong64-cross

# Debian's libc linker script uses absolute cross-prefix paths. Make them
# relative to the sysroot so LLD does not prepend the sysroot twice.
RUN sed -i 's@/usr/loongarch64-linux-gnu/@/@g' /usr/loongarch64-linux-gnu/lib/libc.so

# libcrypt is packaged separately from glibc in Debian Ports.
ADD --checksum=sha256:9e15a5c68280325ad4a5342bb928438ae4273fe03bf1d63b606163c9fc4dba71 \
    https://snapshot.debian.org/archive/debian-ports/20240812T192057Z/pool-loong64/main/libx/libxcrypt/libcrypt-dev_4.4.36-4_loong64.deb \
    /tmp/libcrypt-dev.deb
ADD --checksum=sha256:cf9669e4ee3b3c041e3431fc3d2ea89302a59a585bda2d7d083247c27cfd9ddd \
    https://snapshot.debian.org/archive/debian-ports/20240812T192057Z/pool-loong64/main/libx/libxcrypt/libcrypt1_4.4.36-4_loong64.deb \
    /tmp/libcrypt1.deb
RUN dpkg-deb -x /tmp/libcrypt-dev.deb /tmp/crypt && \
    dpkg-deb -x /tmp/libcrypt1.deb /tmp/crypt && \
    cp -a /tmp/crypt/usr/lib/loongarch64-linux-gnu/. /usr/loongarch64-linux-gnu/lib/ && \
    cp -a /tmp/crypt/usr/include/. /usr/loongarch64-linux-gnu/include/ && \
    rm -rf /tmp/crypt /tmp/libcrypt-dev.deb /tmp/libcrypt1.deb
