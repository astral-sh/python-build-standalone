{% include 'base.debian13.Dockerfile' %}

RUN apt-get install mmdebstrap gpgv debian-ports-archive-keyring
# mmdebstrap's APT hooks use file descriptors above 9.
RUN ln -sf bash /bin/sh

# The 2024 Debian Ports key has expired. Verify its signature and pin the
# authenticated InRelease so another signed snapshot cannot be substituted.
RUN echo '12a48a67e7880fa5c6398e66d01d9306f65b4baba11df4eb317674a7919f3439  snapshot.debian.org_archive_debian-ports_20240812T192057Z_dists_unstable_InRelease' \
        > /loong64-metadata.sha256
RUN mmdebstrap --variant=extract --mode=root \
    --skip=chroot/mount,cleanup/apt/lists \
    --architectures=loong64 \
    --keyring=/usr/share/keyrings/debian-ports-archive-keyring-removed.gpg \
    --aptopt='Acquire::Check-Valid-Until "false"' \
    --aptopt='Acquire::Retries "5"' \
    --aptopt='APT::Update::Error-Mode "any"' \
    --aptopt='DPkg::Chroot-Directory ""' \
    --aptopt='Apt::Key::gpgvcommand "/usr/libexec/mmdebstrap/gpgvnoexpkeysig"' \
    --aptopt='APT::Update::Post-Invoke { "cd /sysroot/var/lib/apt/lists && sha256sum --check --strict /loong64-metadata.sha256"; }' \
    --include=libc6-dev,linux-libc-dev,libcrypt-dev,libgcc-14-dev,libstdc++-14-dev \
    unstable /sysroot \
    'deb [signed-by=01C2D6F3D1A46AD1C0DC2F3D8D69674688B6CB36!] https://snapshot.debian.org/archive/debian-ports/20240812T192057Z/ unstable main'

# Keep the native multiarch layout, including the merged-/usr aliases used
# by libc's linker script and the ELF interpreter.
RUN mkdir -p /target/usr && \
    mv /sysroot/usr/include /sysroot/usr/lib /sysroot/usr/lib64 /target/usr/ && \
    ln -s usr/lib /target/lib && \
    ln -s usr/lib64 /target/lib64

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

COPY --from=0 /target/ /usr/loongarch64-linux-gnu/
