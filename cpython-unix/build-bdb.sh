#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "db-${BDB_VERSION}.tar.gz"

pushd "db-${BDB_VERSION}/build_unix"

CONFIGURE_FLAGS="--enable-dbm --disable-shared"

# configure looks for pthread_yield(), which was dropped from glibc 2.34.
# Its replacement is sched_yield(). Fortunately, bdb's source code will fall
# back to sched_yield() if pthread_yield() isn't available. So we just lie
# to configure and tell it pthread_yield() isn't available.
CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_pthread_yield=no"

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"

if [ "${CC}" = "clang" ]; then
    # deprecated-non-prototype gets very chatty with Clang 15. Suppress it.
    CFLAGS="${CFLAGS} -Wno-deprecated-non-prototype"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" ../dist/configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    ${CONFIGURE_FLAGS}

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"
