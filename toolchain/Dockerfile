# The resulting image has build tools (gcc, make, binutils) from Debian Trixie
# and a small sysroot built from Jessie (x86-64) or Stretch (arm64) packages.
# The sysroot allows the resulting LLVM and GCC runtime libraries to work with
# older glibc versions.
FROM docker.io/library/debian:trixie-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132 AS base

ARG TARGETARCH
ARG BUILDARCH
ARG DEBIAN_SNAPSHOT=20260824T000000Z

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]

# Bootstrap TLS trust before APT installs ca-certificates and OpenSSL. This
# package hash comes from the signed Trixie snapshot metadata.
ADD --checksum=sha256:ef590f89563aa4b46c8260d49d1cea0fc1b181d19e8df3782694706adf05c184 --chmod=644 https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/pool/main/c/ca-certificates/ca-certificates_20250419_all.deb /tmp/ca-certificates.deb

RUN <<EOF
case "${TARGETARCH}" in amd64|arm64) ;; *) exit 1 ;; esac
if [ "${BUILDARCH}" != "${TARGETARCH}" ]; then
    echo 'Use a native Docker builder; cross-architecture builds are not supported.' >&2
    exit 1
fi
dpkg-deb --extract /tmp/ca-certificates.deb /tmp/ca-certificates
mkdir -p /etc/ssl/certs
cat /tmp/ca-certificates/usr/share/ca-certificates/mozilla/*.crt > /etc/ssl/certs/ca-certificates.crt
# The minimal image does not yet have OpenSSL's default CA path.
printf '%s\n' 'Acquire::https::CaInfo "/etc/ssl/certs/ca-certificates.crt";' > /etc/apt/apt.conf.d/99https-ca
rm -rf /tmp/ca-certificates /tmp/ca-certificates.deb
# Replace the image's rolling repositories, retaining signature verification.
rm -f /etc/apt/sources.list.d/debian.sources
cat > /etc/apt/sources.list <<SOURCES
deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie main
deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie-updates main
deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/ trixie-security main
SOURCES
# Fetch the pinned Trixie package lists once for both downstream stages.
apt-get update
EOF

# Construct a sysroot for the target architecture
FROM base AS target-amd64
ENV SYSROOT=/opt/sysroots/jessie-x86_64 SYSROOT_PKG_SOURCE=jessie

FROM base AS target-arm64
ENV SYSROOT=/opt/sysroots/stretch-aarch64 SYSROOT_PKG_SOURCE=stretch

FROM target-${TARGETARCH} AS target

# Resolve and extract the old userspace separately from the build environment.
FROM target AS sysroot
ARG JESSIE_SNAPSHOT=20230322T152120Z
ARG STRETCH_SNAPSHOT=20230423T032736Z
RUN apt-get install -y --no-install-recommends \
    ca-certificates mmdebstrap gpgv

# mmdebstrap's APT hooks can redirect file descriptors above 9, which dash
# rejects. Use bash only in this stage, not in the final image.
RUN ln -sf bash /bin/sh

RUN <<'EOF'
mkdir -p "${SYSROOT}"

# Match the signed, checksum-pinned snapshots in cpython-unix/build.debian13*.Dockerfile.
# Update the snapshot dates, signing keys, and metadata hashes together.
case "${SYSROOT_PKG_SOURCE}" in
    jessie)
        snapshot=${JESSIE_SNAPSHOT}
        archive_key=126C0D24BD8A2942CC7DF8AC7638D0442B90D010
        security_key=D21169141CECD440F2EB8DDA9D6D8F6BC857C906
        release_sha256=ff4cbf89abb58afa73b08f1b21ebaeed9a513e5d848c8c146fdddfa6ca39429a
        security_sha256=4ed764a6a2317c27e644b6502ac0f3a4d3eb25a859c5199e29071b11f332ac75
        ;;
    stretch)
        snapshot=${STRETCH_SNAPSHOT}
        archive_key=16E90B3FDF65EDE3AA7F323C04EE7237B7D453EC
        security_key=379483D8B60160B155B372DDAA8E81B4331F7F50
        release_sha256=fe55c42941dd43102b9490af1678e7962ea1e257ccb8f942b43770475c336eb3
        security_sha256=cb3eb154bf0311d53c98eab79692e55aae49a4bcf13c23bd12943a4fb5a0b05f
        ;;
esac

printf '%s  %s\n' \
    "${release_sha256}" "snapshot.debian.org_archive_debian_${snapshot}_dists_${SYSROOT_PKG_SOURCE}_Release" \
    "${security_sha256}" "snapshot.debian.org_archive_debian-security_${snapshot}_dists_${SYSROOT_PKG_SOURCE}_updates_InRelease" \
    > /sysroot-metadata.sha256

# Create a sysroot with glibc, zlib, kernel headers and their dependencies.
# See the comments in cpython-unix/build.debian13* for details.
mmdebstrap --variant=extract --mode=root \
    --skip=chroot/mount,cleanup/apt/lists \
    --architectures="${TARGETARCH}" \
    --keyring=/usr/share/keyrings/debian-archive-removed-keys.gpg \
    --aptopt='Acquire::Check-Valid-Until "false"' \
    --aptopt='APT::Update::Error-Mode "any"' \
    --aptopt='DPkg::Chroot-Directory ""' \
    --aptopt='Apt::Key::gpgvcommand "/usr/libexec/mmdebstrap/gpgvnoexpkeysig"' \
    --aptopt="APT::Update::Post-Invoke { \"cd ${SYSROOT}/var/lib/apt/lists && sha256sum --check --strict /sysroot-metadata.sha256\"; }" \
    --include=libc6,libc6-dev,linux-libc-dev,zlib1g-dev,symlinks \
    "${SYSROOT_PKG_SOURCE}" "${SYSROOT}" \
    "deb [signed-by=${archive_key}!] https://snapshot.debian.org/archive/debian/${snapshot}/ ${SYSROOT_PKG_SOURCE} main" \
    "deb [signed-by=${security_key}!] https://snapshot.debian.org/archive/debian-security/${snapshot}/ ${SYSROOT_PKG_SOURCE}/updates main"

# Run the old userspace's native utility to make absolute symlinks relative.
# Chroot keeps link targets inside the sysroot, not Trixie.
# Leave linker scripts unchanged: ld resolves their absolute paths via --sysroot.
chroot "${SYSROOT}" /usr/bin/symlinks -cr /

# Export the library/header trees, including the x86-64 loader directory.
mkdir /sysroot-export
for directory in lib lib64 usr; do
    if [[ -e ${SYSROOT}/${directory} || -L ${SYSROOT}/${directory} ]]; then
        cp -a "${SYSROOT}/${directory}" /sysroot-export/
    fi
done
EOF

FROM target AS builder
ARG GCC_VERSION=15.2.0
ARG GCC_SHA256=438fd996826b0c82485a29da03a72d71d6e3541a83ec702df4271f6fe025d24e
ARG LLVM_VERSION=23.1.1
ARG LLVM_SHA256=ebe9be46fe8756d58c5b198ffad0fa2a766257add81a4dc52179bfacc7888ee6

ENV GCC_VERSION=${GCC_VERSION} \
    GCC_ARCHIVE=/opt/sources/gcc.tar.xz \
    LLVM_VERSION=${LLVM_VERSION} \
    LLVM_ARCHIVE=/opt/sources/llvm.tar.xz

RUN <<'EOF'
apt-get install -y --no-install-recommends \
    autoconf \
    automake \
    binutils \
    binutils-dev \
    bison \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    file \
    flex \
    gawk \
    git \
    libgmp-dev \
    libisl-dev \
    libmpc-dev \
    libmpfr-dev \
    libtool \
    ninja-build \
    patch \
    pkg-config \
    python3 \
    shellcheck \
    texinfo \
    unzip \
    xz-utils \
    zstd

# LLVMgold needs this API header, not Trixie's full /usr/include search path.
# TODO: Remove once lld is used rather than ld.gold.
install -d /opt/binutils-headers
cp /usr/include/plugin-api.h /opt/binutils-headers/
rm -rf /var/lib/apt/lists/*
EOF

# Copy only the sysroot.
COPY --from=sysroot --chown=0:0 /sysroot-export/ ${SYSROOT}/

ADD --checksum=sha256:${GCC_SHA256} --chmod=644 \
    https://ftp.gnu.org/gnu/gcc/gcc-${GCC_VERSION}/gcc-${GCC_VERSION}.tar.xz \
    /opt/sources/gcc.tar.xz
ADD --checksum=sha256:${LLVM_SHA256} --chmod=644 \
    https://github.com/llvm/llvm-project/releases/download/llvmorg-${LLVM_VERSION}/llvm-project-${LLVM_VERSION}.src.tar.xz \
    /opt/sources/llvm.tar.xz

# ADD --chmod also sets the mode on newly created parent directories.
RUN chmod 755 /opt/sources \
    && groupadd -g 1000 build \
    && useradd -m -u 1000 -g 1000 -d /build -s /bin/bash build

USER build:build
WORKDIR /build
CMD ["/bin/bash"]
