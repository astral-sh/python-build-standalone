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
