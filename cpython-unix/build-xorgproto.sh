#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

pkg-config --version

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig

tar -xf xorgproto-${XORGPROTO_VERSION}.tar.gz
pushd xorgproto-${XORGPROTO_VERSION}

if [[ "${TARGET_TRIPLE}" = loongarch64* ]]; then
    rm -f config.guess.sub config.sub
    curl -sSL -o config.guess 'https://git.savannah.gnu.org/cgit/config.git/plain/config.guess'
    curl -sSL -o config.sub 'https://git.savannah.gnu.org/cgit/config.git/plain/config.sub'
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out
