#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "m4-${M4_VERSION}.tar.xz"

pushd "m4-${M4_VERSION}"

CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" LDFLAGS="${EXTRA_HOST_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --prefix=/tools/host

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"
