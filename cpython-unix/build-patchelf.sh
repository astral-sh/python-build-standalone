#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf patchelf-${PATCHELF_VERSION}.tar.bz2

pushd patchelf-${PATCHELF_VERSION}

CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" \
    ./configure \
        --build=${BUILD_TRIPLE} \
        --host=${TARGET_TRIPLE} \
        --prefix=/tools/host

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out

# Update DT_NEEDED to use the host toolchain's shared libraries, otherwise
# the defaults of the OS may be used, which would be too old. We run the
# patched binary afterwards to verify it works without LD_LIBRARY_PATH
# modification.
if [ -d /tools/${TOOLCHAIN}/lib ]; then
    LD_LIBRARY_PATH=/tools/${TOOLCHAIN}/lib src/patchelf --replace-needed libstdc++.so.6 /tools/${TOOLCHAIN}/lib/libstdc++.so.6 ${ROOT}/out/tools/host/bin/patchelf
    LD_LIBRARY_PATH=/tools/${TOOLCHAIN}/lib src/patchelf --replace-needed libgcc_s.so.1 /tools/${TOOLCHAIN}/lib/libgcc_s.so.1 ${ROOT}/out/tools/host/bin/patchelf
fi

${ROOT}/out/tools/host/bin/patchelf --version
