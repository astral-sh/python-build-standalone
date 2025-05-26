#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

tar -xf binutils-${BINUTILS_VERSION}.tar.xz
mkdir binutils-objdir
pushd binutils-objdir

# gprofng requires a bison newer than what we have. So just disable it.
../binutils-${BINUTILS_VERSION}/configure \
    --build=x86_64-unknown-linux-gnu \
    --prefix=/tools/host \
    --enable-plugins \
    --enable-gprofng=no \
    --disable-nls \
    --with-sysroot=/

make -j `nproc`
make install -j `nproc` DESTDIR=/build/out

popd
