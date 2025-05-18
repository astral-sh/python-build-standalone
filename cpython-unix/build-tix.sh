#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/deps/bin:${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

# We need the tcl/tk source extracted because tix looks for private symbols.
tar -xf tcl${TCL_VERSION}-src.tar.gz
tar -xf tk${TK_VERSION}-src.tar.gz

tar -xf tix-${TIX_VERSION}.tar.gz

cd cpython-source-deps-tix-${TIX_VERSION}

# Yes, really.
chmod +x configure

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -DUSE_INTERP_RESULT"

# Error by default in Clang 16.
if [ "${CC}" = "clang" ]; then
    CFLAGS="${CFLAGS} -Wno-error=implicit-function-declaration -Wno-error=incompatible-function-pointer-types"
fi

if [[ "${PYBUILD_PLATFORM}" = macos* ]]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/include"
    EXTRA_CONFIGURE_FLAGS="--without-x"
else
    EXTRA_CONFIGURE_FLAGS="--x-includes=/tools/deps/include --x-libraries=/tools/deps/lib"
fi

# -DUSE_INTERP_RESULT is to allow tix to use deprecated fields or something
# like that.
CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-tcl=${TOOLS_PATH}/deps/lib \
    --with-tk=${TOOLS_PATH}/deps/lib \
    --enable-shared=no \
    ${EXTRA_CONFIGURE_FLAGS}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out

# For some reason libtk*.a have weird permissions. Fix that.
chmod 644 ${ROOT}/out/tools/deps/lib/Tix*/libTix*.a
