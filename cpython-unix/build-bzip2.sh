#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

if [ -e ${TOOLS_PATH}/host/bin/${TOOLCHAIN_PREFIX}ar ]; then
    AR=${TOOLS_PATH}/host/bin/${TOOLCHAIN_PREFIX}ar
else
    AR=ar
fi

# Copy compiler-rt builtins library for static aarch64-musl builds
if [ "${TARGET_TRIPLE}" = "aarch64-unknown-linux-musl" ] && [ "${CC}" = "musl-clang" ] && [ -n "${STATIC}" ]; then
    # musl-clang eliminates default library search paths, so copy compiler-rt builtins to accessible location
    for lib in ${TOOLS_PATH}/${TOOLCHAIN}/lib/clang/*/lib/linux/libclang_rt.builtins-aarch64.a; do
        if [ -e "$lib" ]; then
            filename=$(basename "$lib")
            if [ -e "${TOOLS_PATH}/host/lib/${filename}" ]; then
                echo "warning: ${filename} already exists"
            fi
            cp "$lib" ${TOOLS_PATH}/host/lib/
        fi
    done
fi

tar -xf bzip2-${BZIP2_VERSION}.tar.gz

pushd bzip2-${BZIP2_VERSION}

make -j ${NUM_CPUS} install \
    AR=${AR} \
    CC="${CC}" \
    CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" \
    LDFLAGS="${EXTRA_TARGET_LDFLAGS}" \
    PREFIX=${ROOT}/out/tools/deps
