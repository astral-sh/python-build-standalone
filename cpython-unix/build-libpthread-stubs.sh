#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

pkg-config --version

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig

tar -xf "libpthread-stubs-${LIBPTHREAD_STUBS_VERSION}.tar.gz"
pushd "libpthread-stubs-${LIBPTHREAD_STUBS_VERSION}"

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps

make -j "$(nproc)"
make -j "$(nproc)" install DESTDIR="${ROOT}/out"
