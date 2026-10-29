#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf "libxcb-${LIBXCB_VERSION}.tar.gz"
pushd "libxcb-${LIBXCB_VERSION}"

if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="--disable-shared"
fi

# Libtool may drop cross-compilation options from its shared-library link.
# Include them in CC so it invokes the target compiler with the same sysroot.
# https://www.gnu.org/software/libtool/manual/html_node/Stripped-link-flags.html
LIBTOOL_CC="${CC}"
read -r -a TARGET_LDFLAGS <<< "${EXTRA_TARGET_LDFLAGS}"
for flag in "${TARGET_LDFLAGS[@]}"; do
  case "${flag}" in
    --target=*|--sysroot=*|--gcc-install-dir=*|-mfloat-abi=*|-mfpu=*) LIBTOOL_CC="${LIBTOOL_CC} ${flag}" ;;
  esac
done

CC="${LIBTOOL_CC}" CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    ${EXTRA_FLAGS}

make -j "$(nproc)"
make -j "$(nproc)" install DESTDIR="${ROOT}/out"
