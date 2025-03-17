#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf sqlite-autoconf-${SQLITE_VERSION}.tar.gz
pushd sqlite-autoconf-${SQLITE_VERSION}


CONFIGURE_FLAGS="--build=${BUILD_TRIPLE} --host=${TARGET_TRIPLE}"
CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --prefix /tools/deps --disable-shared"

if [ "${TARGET_TRIPLE}" = "aarch64-apple-ios" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_search_system=no"
elif [ "${TARGET_TRIPLE}" = "x86_64-apple-ios" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_search_system=no"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -DSQLITE_ENABLE_DBSTAT_VTAB -DSQLITE_ENABLE_FTS3 -DSQLITE_ENABLE_FTS3_PARENTHESIS -DSQLITE_ENABLE_FTS3_TOKENIZER -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure ${CONFIGURE_FLAGS}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
