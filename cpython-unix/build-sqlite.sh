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
CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --prefix=/tools/deps --disable-shared"

if [ "${TARGET_TRIPLE}" = "aarch64-apple-ios" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_search_system=no"
elif [ "${TARGET_TRIPLE}" = "x86_64-apple-ios" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_search_system=no"
fi

# The SQLite autosetup looks for the C++ compiler if the variable is set and will fail if it's not
# found, even if it's not needed. We don't actually have a C++ compiler in some builds, so ensure
# it's not looked for.
unset CXX

CC_FOR_BUILD="${HOST_CC}" CFLAGS="${EXTRA_TARGET_CFLAGS} -DSQLITE_ENABLE_DBSTAT_VTAB -DSQLITE_ENABLE_FTS3 -DSQLITE_ENABLE_FTS3_PARENTHESIS -DSQLITE_ENABLE_FTS3_TOKENIZER -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure ${CONFIGURE_FLAGS}

make -j ${NUM_CPUS} libsqlite3.a
make install-lib DESTDIR=${ROOT}/out
make install-headers DESTDIR=${ROOT}/out
make install-pc DESTDIR=${ROOT}/out
