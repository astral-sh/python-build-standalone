#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/deps/bin:${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

tar -xf tk${TK_VERSION}-src.tar.gz

pushd tk*/unix

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC"
LDFLAGS="${EXTRA_TARGET_LDFLAGS}"

if [[ "${PYBUILD_PLATFORM}" = macos* ]]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/include -Wno-availability"
    CFLAGS="${CFLAGS} -Wno-deprecated-declarations -Wno-unknown-attributes -Wno-typedef-redefinition"
    LDFLAGS="-L${TOOLS_PATH}/deps/lib"
    EXTRA_CONFIGURE_FLAGS="--enable-aqua=yes --without-x"
else
    EXTRA_CONFIGURE_FLAGS="--x-includes=${TOOLS_PATH}/deps/include --x-libraries=${TOOLS_PATH}/deps/lib"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-tcl=${TOOLS_PATH}/deps/lib \
    --enable-shared=no \
    --enable-threads \
    ${EXTRA_CONFIGURE_FLAGS}

# Remove wish, since we don't need it.
if [[ "${PYBUILD_PLATFORM}" != macos* ]]; then
    sed -i 's/all: binaries libraries doc/all: libraries/' Makefile
    sed -i 's/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE) ${WISH_EXE}/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE)/' Makefile
fi

# For some reason musl isn't link libXau and libxcb. So we hack the Makefile
# to do what we want.
if [ "${CC}" = "musl-clang" ]; then
    sed -i 's/-ldl  -lpthread /-ldl  -lpthread -lXau -lxcb/' tkConfig.sh
    sed -i 's/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread -lXau -lxcb/' Makefile
fi

make -j ${NUM_CPUS}
touch wish
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

# For some reason libtk*.a have weird permissions. Fix that.
chmod 644 /${ROOT}/out/tools/deps/lib/libtk*.a

rm ${ROOT}/out/tools/deps/bin/wish*
