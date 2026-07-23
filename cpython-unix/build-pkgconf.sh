#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "pkgconf-${PKGCONF_VERSION}.tar.xz"

pushd "pkgconf-${PKGCONF_VERSION}"

CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" LDFLAGS="${EXTRA_HOST_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --prefix=/tools/host \
    --disable-shared \
    --disable-dependency-tracking \
    --with-system-libdir=/usr/lib \
    --with-system-includedir=/usr/include

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"

ln -s pkgconf "${ROOT}/out/tools/host/bin/pkg-config"

"${ROOT}/out/tools/host/bin/pkg-config" --version
