#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf libxcb-${LIBXCB_VERSION}.tar.gz
pushd libxcb-${LIBXCB_VERSION}

if [[ "${TARGET_TRIPLE}" = loongarch64* ]]; then
    rm -f build-aux/config.guess build-aux/config.sub
    curl -sSL -o build-aux/config.guess https://github.com/cgitmirror/config/raw/refs/heads/master/config.guess
    curl -sSL -o build-aux/config.sub https://github.com/cgitmirror/config/raw/refs/heads/master/config.sub
fi

if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="--disable-shared"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"  CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    ${EXTRA_FLAGS}

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out
