{% include 'base.debian13.Dockerfile' %}

RUN apt-get install ca-certificates mmdebstrap gpgv

# mmdebstrap's APT hooks can redirect file descriptors above 9, which dash
# rejects. Use bash only in this preparation stage, not in the final image.
RUN ln -sf bash /bin/sh

# Jessie's archive signing keys have expired but are still checked when
# creating the sysroot. Further validation is done by checking the SHA256
# of the Release/InRelease files to protect against replay of older signed indexes.
# These hashes can be obtained using:
# apt install curl gpgv ca-certificates
# curl -fSLO https://snapshot.debian.org/archive/debian/20230322T152120Z/dists/jessie/Release
# curl -fSLO https://snapshot.debian.org/archive/debian/20230322T152120Z/dists/jessie/Release.gpg
# curl -fSLO https://snapshot.debian.org/archive/debian-security/20230322T152120Z/dists/jessie/updates/InRelease
# gpgv --keyring /usr/share/keyrings/debian-archive-removed-keys.gpg Release.gpg Release
# # Validate a good signature with RSA Key 126C0D24BD8A2942CC7DF8AC7638D0442B90D010
# gpgv --keyring /usr/share/keyrings/debian-archive-removed-keys.gpg InRelease
# # Validate a good signature with RSA Key D21169141CECD440F2EB8DDA9D6D8F6BC857C906
# sha256sum Release InRelease
RUN printf '%s\n' \
    'ff4cbf89abb58afa73b08f1b21ebaeed9a513e5d848c8c146fdddfa6ca39429a  snapshot.debian.org_archive_debian_20230322T152120Z_dists_jessie_Release' \
    '4ed764a6a2317c27e644b6502ac0f3a4d3eb25a859c5199e29071b11f332ac75  snapshot.debian.org_archive_debian-security_20230322T152120Z_dists_jessie_updates_InRelease' \
    > /jessie-metadata.sha256

# Create a sysroot with glibc, kernel headers and their dependencies from a
# Jessie snapshot. Do not run maintainer scripts. The expired Jessie signing
# key is verified against the RSA key from a keyring with known removed keys.
# Run APT hooks outside the unpopulated sysroot so the checksum check uses
# Trixie's shell and sha256sum.
# Skip APT list cleanup: it runs another update with empty sources, which
# would remove the pinned metadata and cause the checksum hook to fail.
# The retained lists stay in this preparation stage, not the final image.
RUN mmdebstrap --variant=extract --mode=root \
    --skip=chroot/mount,cleanup/apt/lists \
    --architectures=amd64 \
    --keyring=/usr/share/keyrings/debian-archive-removed-keys.gpg \
    --aptopt='Acquire::Check-Valid-Until "false"' \
    --aptopt='Acquire::Retries "5"' \
    --aptopt='APT::Update::Error-Mode "any"' \
    --aptopt='DPkg::Chroot-Directory ""' \
    --aptopt='Apt::Key::gpgvcommand "/usr/libexec/mmdebstrap/gpgvnoexpkeysig"' \
    --aptopt='APT::Update::Post-Invoke { "cd /sysroot/var/lib/apt/lists && sha256sum --check --strict /jessie-metadata.sha256"; }' \
    --include=libc6,libc6-dev,linux-libc-dev,symlinks \
    jessie /sysroot \
    'deb [signed-by=126C0D24BD8A2942CC7DF8AC7638D0442B90D010!] https://snapshot.debian.org/archive/debian/20230322T152120Z/ jessie main' \
    'deb [signed-by=D21169141CECD440F2EB8DDA9D6D8F6BC857C906!] https://snapshot.debian.org/archive/debian-security/20230322T152120Z/ jessie/updates main'

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
