#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "expat-${EXPAT_VERSION}.tar.xz"

pushd "expat-${EXPAT_VERSION}"

EXPAT_CONFIGURE_FLAGS=()
# Expat 2.8.2 no longer enables /dev/urandom by default. Enable it for
# # x86-64 Linux, whose older glibc target cannot use getrandom().
# https://github.com/libexpat/libexpat/pull/1257
if [[ "${TARGET_TRIPLE}" = x86_64-*-linux-* ]]; then
    # Older Linux targets may not expose newer entropy APIs to configure.
    EXPAT_CONFIGURE_FLAGS+=(--with-dev-urandom)
fi

# xmlwf isn't needed by CPython.
# Disable -fexceptions because we don't need it and it adds a dependency on libgcc_s, which
# is softly undesirable.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    --disable-shared \
    --without-examples \
    --without-tests \
    --without-xmlwf \
    "${EXPAT_CONFIGURE_FLAGS[@]}" \
    ax_cv_check_cflags___fexceptions=no

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"
