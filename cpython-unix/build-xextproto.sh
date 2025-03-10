#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

pkg-config --version

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig

tar -xf xextproto-${XEXTPROTO_VERSION}.tar.gz
pushd xextproto-${XEXTPROTO_VERSION}

EXTRA_CONFIGURE_FLAGS=
if [ -n "${CROSS_COMPILING}" ]; then
    if echo "${TARGET_TRIPLE}" | grep -q -- "-unknown-linux-musl"; then
    # xextproto does not support configuration of musl targets so we pretend the target matches the
    # build triple and enable cross-compilation manually
    TARGET_TRIPLE="$(echo "${TARGET_TRIPLE}" | sed -e 's/-unknown-linux-musl/-unknown-linux-gnu/g')"
    EXTRA_CONFIGURE_FLAGS="cross_compiling=yes"
    fi
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    ${EXTRA_CONFIGURE_FLAGS}

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out
