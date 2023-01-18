#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf gdbm-${GDBM_VERSION}.tar.gz

pushd gdbm-${GDBM_VERSION}

# CPython setup.py looks for libgdbm_compat and gdbm-ndbm.h,
# which require --enable-libgdbm-compat.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    --enable-libgdbm-compat

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
