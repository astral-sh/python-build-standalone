#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xzf "util-macros-${X11_UTIL_MACROS_VERSION}.tar.gz"
pushd "util-macros-${X11_UTIL_MACROS_VERSION}"
CFLAGS="${EXTRA_TARGET_CFLAGS}" CPPFLAGS="${EXTRA_TARGET_CFLAGS}" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps

make -j "$(nproc)"
make -j "$(nproc)" install DESTDIR="${ROOT}/out"
