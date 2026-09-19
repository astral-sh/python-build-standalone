#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Build bootstrap Clang with Trixie's GCC, then LLVM with the custom GCC runtimes.
set -euo pipefail
umask 022

if [[ $(uname -m) == x86_64 ]]; then
    GNU_TARGET=x86_64-linux-gnu
    LLVM_TRIPLE=x86_64-unknown-linux-gnu
    SYSROOT=/opt/sysroots/jessie-x86_64
else
    GNU_TARGET=aarch64-linux-gnu
    LLVM_TRIPLE=aarch64-unknown-linux-gnu
    SYSROOT=/opt/sysroots/stretch-aarch64
fi
GCC_MAJOR=${GCC_VERSION%%.*}

# Use a clean compiler environment.
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH LD_LIBRARY_PATH
unset GCC_EXEC_PREFIX COMPILER_PATH CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
unset CLANG_NO_DEFAULT_CONFIG PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR
export PATH=/usr/local/bin:/usr/bin:/bin LC_ALL=C.UTF-8

mkdir -p /build/llvm/src
tar -xf /opt/sources/llvm.tar.xz --strip-components=1 -C /build/llvm/src

# Build a bootstrap clang against the system (Trixie) headers and libraries.
cmake -S /build/llvm/src/llvm -B /build/llvm/bootstrap \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    "-DLLVM_HOST_TRIPLE=${LLVM_TRIPLE}" \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLVM_INCLUDE_BENCHMARKS=OFF \
    -DCMAKE_C_COMPILER=/usr/bin/gcc \
    -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
    -DLLVM_ENABLE_ZLIB=OFF \
    -DLLVM_TARGETS_TO_BUILD=Native \
    -DLLVM_ENABLE_PROJECTS=clang
cmake --build /build/llvm/bootstrap --parallel "${PARALLEL}" \
    --target clang clang-resource-headers
ln -sf clang /build/llvm/bootstrap/bin/clang++

# BOLT's runtime build does not inherit CMake flags. Give bootstrap Clang the
# sysroot and GCC paths directly, including the lib64 search path for AArch64.
cat > /build/llvm/bootstrap/bin/clang.cfg <<EOF
--sysroot=${SYSROOT}
--gcc-install-dir=/build/gcc/install/toolchain/lib/gcc/${GNU_TARGET}/${GCC_MAJOR}
--start-no-unused-arguments
-L/build/gcc/install/toolchain/lib64
-Wl,-rpath-link,/build/gcc/install/toolchain/lib64
--end-no-unused-arguments
EOF
cp /build/llvm/bootstrap/bin/clang.cfg /build/llvm/bootstrap/bin/clang++.cfg

# Build the final toolchain with runtime paths relative to its installation.
export PKG_CONFIG_LIBDIR="${SYSROOT}/usr/lib/${GNU_TARGET}/pkgconfig:${SYSROOT}/usr/share/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="${SYSROOT}"
cmake -S /build/llvm/src/llvm -B /build/llvm/final \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    "-DLLVM_HOST_TRIPLE=${LLVM_TRIPLE}" \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLVM_INCLUDE_BENCHMARKS=OFF \
    "-DCMAKE_SYSROOT=${SYSROOT}" \
    -DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER \
    -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
    -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY \
    -DCMAKE_BUILD_RPATH=/build/gcc/install/toolchain/lib64 \
    -DLLVM_ENABLE_ZLIB=FORCE_ON \
    -DCMAKE_C_COMPILER=/build/llvm/bootstrap/bin/clang \
    -DCMAKE_CXX_COMPILER=/build/llvm/bootstrap/bin/clang++ \
    -DCMAKE_ASM_COMPILER=/build/llvm/bootstrap/bin/clang \
    "-DCMAKE_C_COMPILER_TARGET=${LLVM_TRIPLE}" \
    "-DCMAKE_CXX_COMPILER_TARGET=${LLVM_TRIPLE}" \
    "-DCMAKE_ASM_COMPILER_TARGET=${LLVM_TRIPLE}" \
    -DCMAKE_INSTALL_PREFIX=/build/llvm-install \
    "-DCMAKE_INSTALL_RPATH=\$ORIGIN/../lib;\$ORIGIN" \
    -DLLVM_ENABLE_PROJECTS='bolt;clang;compiler-rt;lld' \
    -DCOMPILER_RT_DEFAULT_TARGET_ONLY=ON \
    -DLLVM_BINUTILS_INCDIR=/opt/binutils-headers \
    -DLLVM_INSTALL_UTILS=ON
cmake --build /build/llvm/final --parallel "${PARALLEL}"
cmake --install /build/llvm/final
