#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PREFIX="/tools/deps"

tar -xf "zstd-${ZSTD_VERSION}.tar.gz"

pushd "zstd-${ZSTD_VERSION}/lib"

if [ "${CC}" = "musl-clang" ]; then
    # In order to build the library with intrinsics, we need musl-clang to find
    # headers that provide access to the intrinsics, as they are not provided by musl. These are
    # part of the include files that are part of clang. But musl-clang eliminates them from the
    # default include path. So copy them into place.
    for h in ${TOOLS_PATH}/${TOOLCHAIN}/lib/clang/*/include/*intrin.h ${TOOLS_PATH}/${TOOLCHAIN}/lib/clang/*/include/{__wmmintrin_aes.h,__wmmintrin_pclmul.h,emmintrin.h,immintrin.h,mm_malloc.h,arm_neon.h,arm_neon_sve_bridge.h,arm_bf16.h,arm_fp16.h,arm_acle.h,arm_vector_types.h}; do
        filename=$(basename "$h")
        if [ -f "$h" ]; then
            if [ -e "${TOOLS_PATH}/host/include/${filename}" ]; then
                echo "warning: ${filename} already exists"
            fi
            cp "$h" "${TOOLS_PATH}/host/include/"
        else
            echo "warning: ${filename} not found (skipping)"
        fi
    done
    EXTRA_TARGET_CFLAGS="${EXTRA_TARGET_CFLAGS} -I${TOOLS_PATH}/host/include/"

    # musl 1.2.2 lacks qsort_r, so select zstd's standard qsort fallback.
    if [ -z "${STATIC}" ]; then
        EXTRA_TARGET_CFLAGS="${EXTRA_TARGET_CFLAGS} -DZDICT_QSORT=ZDICT_QSORT_C90"
    fi
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -DZSTD_MULTITHREAD -O3" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" make -j "${NUM_CPUS}" VERBOSE=1 libzstd.a
make -j "${NUM_CPUS}" install-static DESTDIR="${ROOT}/out"
make -j "${NUM_CPUS}" install-includes DESTDIR="${ROOT}/out"
MT=1 make -j "${NUM_CPUS}" install-pc DESTDIR="${ROOT}/out"
