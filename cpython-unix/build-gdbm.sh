#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "gdbm-${GDBM_VERSION}.tar.gz"

pushd "gdbm-${GDBM_VERSION}"

CONFIGURE_FLAGS="--disable-shared --enable-libgdbm-compat"

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"

if [ "${CC}" = "clang" ]; then
    # Suppress warnings if needed
    CFLAGS="${CFLAGS} -Wno-deprecated-non-prototype"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    ${CONFIGURE_FLAGS}

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"

popd
