#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf xz-${XZ_VERSION}.tar.gz

pushd xz-${XZ_VERSION}

EXTRA_CONFIGURE_FLAGS=

# musl-clang injects flags that are not used during compilation,
# e.g. -fuse-ld=musl-clang. These raise warnings that can be ignored but
# cause the -Werror check to fail. Skip the check.
if [ "${CC}" = "musl-clang" ]; then
    EXTRA_CONFIGURE_FLAGS="${EXTRA_CONFIGURE_FLAGS} SKIP_WERROR_CHECK=yes"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CCASFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    --disable-xz \
    --disable-xzdec \
    --disable-lzmadec \
    --disable-lzmainfo \
    --disable-lzma-links \
    --disable-scripts \
    ${EXTRA_CONFIGURE_FLAGS}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
