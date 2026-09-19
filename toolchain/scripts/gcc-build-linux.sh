#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Build GCC runtime libraries against a sysroot for inclusion with LLVM
set -euo pipefail
umask 022

if [[ $(uname -m) == x86_64 ]]; then
    triple=x86_64-linux-gnu
    SYSROOT=/opt/sysroots/jessie-x86_64
else
    triple=aarch64-linux-gnu
    SYSROOT=/opt/sysroots/stretch-aarch64
fi

# Use a clean compiler environment.
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH LD_LIBRARY_PATH
unset GCC_EXEC_PREFIX COMPILER_PATH CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
export PATH=/usr/local/bin:/usr/bin:/bin LC_ALL=C.UTF-8

mkdir -p /build/gcc/src /build/gcc/obj /build/gcc/install
tar -xf /opt/sources/gcc.tar.xz --strip-components=1 -C /build/gcc/src

cd /build/gcc/obj

#  --with-sysroot selects the old libc headers and libraries for the target runtimes.
CC=/usr/bin/gcc CXX=/usr/bin/g++ /build/gcc/src/configure \
    --build="${triple}" \
    --host="${triple}" \
    --target="${triple}" \
    --prefix=/toolchain \
    --libdir=/toolchain/lib \
    --with-sysroot="${SYSROOT}" \
    --with-native-system-header-dir=/usr/include \
    --with-gcc-major-version-only \
    --enable-languages=c,c++ \
    --enable-multiarch \
    --enable-default-pie \
    --enable-__cxa_atexit \
    --enable-linker-build-id \
    --disable-gnu-unique-object \
    --disable-bootstrap \
    --disable-multilib \
    --disable-nls \
    --disable-lto \
    --disable-plugin \
    --disable-libstdcxx-pch \
    --disable-libsanitizer \
    --disable-libgomp \
    --disable-libquadmath \
    --disable-libssp \
    --disable-libvtv

# Build the compiler, then libgcc, libstdc++, and libatomic for the sysroot.
make -j "${PARALLEL}" all-gcc
make -j "${PARALLEL}" all-target-libgcc all-target-libstdc++-v3 all-target-libatomic
make DESTDIR=/build/gcc/install \
    install-gcc install-target-libgcc install-target-libstdc++-v3 install-target-libatomic

# Export the runtime libraries and headers for llvm-assemble-toolchain.sh.
mkdir -p /build/out-support/include /build/out-support/lib/gcc
cp -a /build/gcc/install/toolchain/include/c++ /build/out-support/include/
cp -a "/build/gcc/install/toolchain/lib/gcc/${triple}" /build/out-support/lib/gcc/
cp -a /build/gcc/install/toolchain/lib64 /build/out-support/
