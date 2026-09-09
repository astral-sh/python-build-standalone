{% include 'base.debian13.Dockerfile' %}

RUN apt-get install ca-certificates mmdebstrap gpgv

# mmdebstrap's APT hooks can redirect file descriptors above 9, which dash
# rejects. Use bash only in this preparation stage, not in the final image.
RUN ln -sf bash /bin/sh

# Retain signature verification while allowing historical key expiry. Pin the
# authenticated Release/InRelease metadata to reject older signed indexes.
# To regenerate these hashes in Trixie with curl, gpgv and debian-archive-keyring:
# curl -fSLO https://snapshot.debian.org/archive/debian/20230423T032736Z/dists/stretch/Release
# curl -fSLO https://snapshot.debian.org/archive/debian/20230423T032736Z/dists/stretch/Release.gpg
# curl -fSLO https://snapshot.debian.org/archive/debian-security/20230423T032736Z/dists/stretch/updates/InRelease
# gpgv --keyring /usr/share/keyrings/debian-archive-removed-keys.gpg --keyring /usr/share/keyrings/debian-archive-keyring.gpg Release.gpg Release
# # Validate a good signature with RSA Key 16E90B3FDF65EDE3AA7F323C04EE7237B7D453EC
# gpgv --keyring /usr/share/keyrings/debian-archive-removed-keys.gpg --keyring /usr/share/keyrings/debian-archive-keyring.gpg InRelease
# # Validate a good signature with RSA Key 379483D8B60160B155B372DDAA8E81B4331F7F50
# sha256sum Release InRelease
RUN printf '%s\n' \
    'fe55c42941dd43102b9490af1678e7962ea1e257ccb8f942b43770475c336eb3  snapshot.debian.org_archive_debian_20230423T032736Z_dists_stretch_Release' \
    'cb3eb154bf0311d53c98eab79692e55aae49a4bcf13c23bd12943a4fb5a0b05f  snapshot.debian.org_archive_debian-security_20230423T032736Z_dists_stretch_updates_InRelease' \
    > /stretch-metadata.sha256

# Create a sysroot with glibc, kernel headers and their dependencies from
# a Stretch snapshop. Do not run maintainer scripts. The expired Stretch signing
# key is verified against the RSA key from a keyring with known removed keys.
# Run APT hooks outside the unpopulated sysroot using Trixie's shell and tools.
# Skip APT list cleanup: it runs another update with empty sources, which
# would remove the pinned metadata and cause the checksum hook to fail.
# The retained lists stay in this preparation stage, not the final image.
RUN mmdebstrap --variant=extract --mode=root \
    --skip=chroot/mount,cleanup/apt/lists \
    --architectures=arm64 \
    --keyring=/usr/share/keyrings/debian-archive-removed-keys.gpg \
    --aptopt='Acquire::Check-Valid-Until "false"' \
    --aptopt='Acquire::Retries "5"' \
    --aptopt='APT::Update::Error-Mode "any"' \
    --aptopt='DPkg::Chroot-Directory ""' \
    --aptopt='Apt::Key::gpgvcommand "/usr/libexec/mmdebstrap/gpgvnoexpkeysig"' \
    --aptopt='APT::Update::Post-Invoke { "cd /sysroot/var/lib/apt/lists && sha256sum --check --strict /stretch-metadata.sha256"; }' \
    --include=libc6,libc6-dev,linux-libc-dev,symlinks \
    stretch /sysroot \
    'deb [signed-by=16E90B3FDF65EDE3AA7F323C04EE7237B7D453EC!] https://snapshot.debian.org/archive/debian/20230423T032736Z/ stretch main' \
    'deb [signed-by=379483D8B60160B155B372DDAA8E81B4331F7F50!] https://snapshot.debian.org/archive/debian-security/20230423T032736Z/ stretch/updates main'

# Absolute symlinks would escape the sysroot into the Trixie host filesystem.
# Run Stretch's symlinks utility inside the sysroot so targets resolve there.
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
COPY --from=0 /sysroot/lib/ /usr/aarch64-linux-gnu/lib/
COPY --from=0 /sysroot/usr/ /usr/aarch64-linux-gnu/usr/
