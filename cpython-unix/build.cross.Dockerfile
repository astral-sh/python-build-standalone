{% include 'base.debian13.Dockerfile' %}

# Use the same authenticated Stretch snapshot as the native AArch64 sysroot.
# Its signing key has expired, so verify it with mmdebstrap's gpgv wrapper and
# pin the signed Release metadata before installing any cross packages.
RUN apt-get install --yes ca-certificates mmdebstrap gpgv
RUN echo 'deb [signed-by=/usr/share/keyrings/debian-archive-removed-keys.gpg] https://snapshot.debian.org/archive/debian/20230423T032736Z/ stretch main' \
        > /etc/apt/sources.list.d/stretch.list && \
    echo 'APT::Update::Error-Mode "any";' >> /etc/apt/apt.conf.d/99cpython-portable

RUN printf 'Package: *-cross\nPin: release n=stretch\nPin-Priority: 900\n' \
        > /etc/apt/preferences.d/stretch-cross

# This is the authenticated Release hash used by build.debian13.Dockerfile.
RUN apt-get -o 'Apt::Key::gpgvcommand=/usr/libexec/mmdebstrap/gpgvnoexpkeysig' update && \
    echo 'fe55c42941dd43102b9490af1678e7962ea1e257ccb8f942b43770475c336eb3  /var/lib/apt/lists/snapshot.debian.org_archive_debian_20230423T032736Z_dists_stretch_Release' \
        | sha256sum --check --strict

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

# The cross packages provide glibc, kernel headers, and GCC runtime/startup
# objects; compilation and linking use the separately supplied LLVM toolchain.
RUN apt-get install \
    libc6-dev-armel-cross libgcc-6-dev-armel-cross \
    libc6-dev-armhf-cross libgcc-6-dev-armhf-cross \
    libc6-dev-ppc64el-cross libgcc-6-dev-ppc64el-cross \
    libc6-dev-s390x-cross libgcc-6-dev-s390x-cross

# Debian's linker scripts contain absolute cross-prefix paths. Make those
# relative to the sysroot so LLD does not prepend the sysroot twice.
RUN for target in arm-linux-gnueabi arm-linux-gnueabihf \
              powerpc64le-linux-gnu s390x-linux-gnu; do \
      for script in libc.so libpthread.so; do \
        sed -i "s@/usr/${target}/@/@g" "/usr/${target}/lib/${script}"; \
      done; \
    done
