#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

# Force linking to static libraries from our dependencies.
# TODO(geofft): This is copied from build-cpython.sh. Really this should
# be done at the end of the build of each dependency, rather than before
# the build of each consumer.
find ${TOOLS_PATH}/deps -name '*.so*' -exec rm {} \;

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
    LDFLAGS="${LDFLAGS} -Wl,--exclude-libs,ALL"
    EXTRA_CONFIGURE_FLAGS="--x-includes=${TOOLS_PATH}/deps/include --x-libraries=${TOOLS_PATH}/deps/lib"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-tcl=${TOOLS_PATH}/deps/lib \
    --enable-shared"${STATIC:+=no}" \
    --enable-threads \
    ${EXTRA_CONFIGURE_FLAGS}

# Remove wish, since we don't need it.
if [[ "${PYBUILD_PLATFORM}" = macos* ]]; then
    sed_args=(-i '' -e)
else
    sed_args=(-i)
fi
sed "${sed_args[@]}" 's/all: binaries libraries doc/all: libraries/' Makefile
sed "${sed_args[@]}" 's/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE) ${WISH_EXE}/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE)/' Makefile

# We are statically linking libX11, and static libraries do not carry
# information about dependencies. pkg-config --static does, but Tcl/Tk's
# build system apparently is too old for that. So we need to manually
# inform the build process that libX11.a needs libxcb.a and libXau.a.
# Note that the order is significant, for static libraries: X11 requires
# xcb, which requires Xau.
MAKE_VARS=(DYLIB_INSTALL_DIR=@rpath)
if [[ "${PYBUILD_PLATFORM}" != macos* ]]; then
    MAKE_VARS+=(X11_LIB_SWITCHES="-lX11 -lxcb -lXau")
fi

make -j ${NUM_CPUS} "${MAKE_VARS[@]}"
touch wish
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out "${MAKE_VARS[@]}"
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

# For some reason libtk*.a have weird permissions. Fix that.
if [ -n "${STATIC}" ]; then
    chmod 644 /${ROOT}/out/tools/deps/lib/libtk*.a
fi

rm ${ROOT}/out/tools/deps/bin/wish*
