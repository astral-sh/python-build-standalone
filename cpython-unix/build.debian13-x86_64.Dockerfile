{% include 'base.debian13.Dockerfile' %}

RUN apt-get install ca-certificates mmdebstrap gpgv

# mmdebstrap's APT hooks can redirect file descriptors above 9, which dash
# rejects. Use bash only in this preparation stage, not in the final image.
RUN ln -sf bash /bin/sh

# Use the same Jessie snapshots as the former native x86-64 build image.
# Extract libc, kernel headers, symlinks, and their dependencies without running
# maintainer scripts. The archived keys and gpgv helper retain signature
# verification while allowing Jessie's expired signing keys.
RUN mmdebstrap --variant=extract --mode=root \
    --skip=chroot/mount \
    --architectures=amd64 \
    --keyring=/usr/share/keyrings/debian-archive-removed-keys.gpg \
    --aptopt='Acquire::Check-Valid-Until "false"' \
    --aptopt='Acquire::Retries "5"' \
    --aptopt='Apt::Key::gpgvcommand "/usr/libexec/mmdebstrap/gpgvnoexpkeysig"' \
    --include=libc6,libc6-dev,linux-libc-dev,symlinks \
    jessie /sysroot \
    'deb https://snapshot.debian.org/archive/debian/20230322T152120Z/ jessie main' \
    'deb https://snapshot.debian.org/archive/debian/20230322T152120Z/ jessie-updates main' \
    'deb https://snapshot.debian.org/archive/debian-security/20230322T152120Z/ jessie/updates main'

# Absolute symlinks would escape the sysroot into the Trixie host filesystem.
# Run Jessie's symlinks utility inside the sysroot so targets resolve there.
# Keep linker scripts unchanged: ld resolves their absolute paths via --sysroot.
RUN chroot /sysroot /usr/bin/symlinks -cr /

# Build tools and host programs run against current Debian Trixie libraries.
{% include 'base.debian13.Dockerfile' %}

# libffi and zlib are used by host Python, independently of the target sysroot.
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

# Copy the native multiarch layout, without mmdebstrap's APT state or packages.
COPY --from=0 /sysroot/lib/ /usr/x86_64-linux-gnu/lib/
COPY --from=0 /sysroot/lib64/ /usr/x86_64-linux-gnu/lib64/
COPY --from=0 /sysroot/usr/ /usr/x86_64-linux-gnu/usr/
