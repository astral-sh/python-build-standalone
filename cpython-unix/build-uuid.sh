#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "util-linux-${UUID_VERSION}.tar.xz"
pushd "util-linux-${UUID_VERSION}"

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"

UUID_CONFIGURE_FLAGS=()
if [[ "${TARGET_TRIPLE}" == *-linux-* ]]; then
    UUID_CONFIGURE_FLAGS+=(--enable-libuuid-force-uuidd)
fi

# The ARMv7 GNU toolchains use glibc with 32-bit time_t. Keep the existing
# compatibility baseline even though timestamps after 2038 are not supported.
case "${TARGET_TRIPLE}" in
    armv7-unknown-linux-gnueabi|armv7-unknown-linux-gnueabihf)
        UUID_CONFIGURE_FLAGS+=(--disable-year2038)
        ;;
esac

# The util-linux configure script requires Linux headers globally, but libuuid
# does not use linux/version.h. Keep HAVE_LINUX_VERSION_H undefined while
# bypassing that check for musl; recheck this when updating util-linux.
if [[ "${TARGET_TRIPLE}" == *-linux-musl* ]]; then
    export ac_cv_header_linux_version_h=unknown
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    --localstatedir=/var \
    --libdir=/tools/deps/lib \
    --disable-all-programs \
    --enable-libuuid \
    --disable-libblkid \
    --disable-libfdisk \
    --disable-liblastlog2 \
    --disable-libmount \
    --disable-libsmartcols \
    --disable-nls \
    --disable-asciidoc \
    --disable-dependency-tracking \
    --without-python \
    --without-systemd \
    --disable-shared \
    --enable-static \
    "${UUID_CONFIGURE_FLAGS[@]}"

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"
