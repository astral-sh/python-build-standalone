#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

tar -xf tcl${TCL_VERSION}-src.tar.gz
pushd tcl${TCL_VERSION}


if [ -n "${STATIC}" ]; then
	if echo "${TARGET_TRIPLE}" | grep -q -- "-unknown-linux-musl"; then
		# tcl misbehaves when performing static musl builds
		# `checking whether musl-clang accepts -g...` fails with a duplicate definition error
		TARGET_TRIPLE="$(echo "${TARGET_TRIPLE}" | sed -e 's/-unknown-linux-musl/-unknown-linux-gnu/g')"
	fi
fi

# Remove packages we don't care about and can pull in unwanted symbols.
rm -rf pkgs/sqlite* pkgs/tdbc*

pushd unix

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include"

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --enable-shared \
    --enable-threads

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out
