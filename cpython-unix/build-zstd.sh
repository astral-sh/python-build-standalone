#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PREFIX="/tools/deps"

tar -xf zstd-${ZSTD_VERSION}.tar.gz

pushd cpython-source-deps-zstd-${ZSTD_VERSION}/lib

if [ "${CC}" = "musl-clang" ]; then
    # In order to build the library with SSE2, BMI, and AVX2 intrinstics, we need musl-clang to find
    # headers that provide access to the intrinsics, as they are not provided by musl. These are
    # part of the include files that are part of clang. But musl-clang eliminates them from the
    # default include path. So copy them into place.
    for h in ${TOOLS_PATH}/${TOOLCHAIN}/lib/clang/*/include/*intrin.h ${TOOLS_PATH}/${TOOLCHAIN}/lib/clang/*/include/{__wmmintrin_aes.h,__wmmintrin_pclmul.h,emmintrin.h,immintrin.h,mm_malloc.h}; do
        filename=$(basename "$h")
        if [ -e "${TOOLS_PATH}/host/include/${filename}" ]; then
            echo "warning: ${filename} already exists"
        fi
        cp "$h" ${TOOLS_PATH}/host/include/
    done
    EXTRA_TARGET_CFLAGS="${EXTRA_TARGET_CFLAGS} -I${TOOLS_PATH}/host/include/"

    # `qsort_r` is only available in musl 1.2.3+ but we use 1.2.2. The zstd source provides a
    # fallback implementation, but they do not have a `configure`-style detection of whether
    # `qsort_r` is actually available so we patch it to include a check for glibc.
    patch -p1 <<EOF
diff --git a/dictBuilder/cover.c b/dictBuilder/cover.c
index 5e6e8bc..6ca72a1 100644
--- a/dictBuilder/cover.c
+++ b/dictBuilder/cover.c
@@ -241,7 +241,7 @@ typedef struct {
   unsigned d;
 } COVER_ctx_t;
 
-#if !defined(_GNU_SOURCE) && !defined(__APPLE__) && !defined(_MSC_VER)
+#if !(defined(_GNU_SOURCE) && defined(__GLIBC__)) && !defined(__APPLE__) && !defined(_MSC_VER)
 /* C90 only offers qsort() that needs a global context. */
 static COVER_ctx_t *g_coverCtx = NULL;
 #endif
@@ -328,7 +328,7 @@ static void stableSort(COVER_ctx_t *ctx) {
     qsort_r(ctx->suffix, ctx->suffixSize, sizeof(U32),
             ctx,
             (ctx->d <= 8 ? &COVER_strict_cmp8 : &COVER_strict_cmp));
-#elif defined(_GNU_SOURCE)
+#elif defined(_GNU_SOURCE) && defined(__GLIBC__)
     qsort_r(ctx->suffix, ctx->suffixSize, sizeof(U32),
             (ctx->d <= 8 ? &COVER_strict_cmp8 : &COVER_strict_cmp),
             ctx);
EOF
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -DZSTD_MULTITHREAD -O3" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" make -j ${NUM_CPUS} VERBOSE=1 libzstd.a
make -j ${NUM_CPUS} install-static DESTDIR=${ROOT}/out
make -j ${NUM_CPUS} install-includes DESTDIR=${ROOT}/out
MT=1 make -j ${NUM_CPUS} install-pc DESTDIR=${ROOT}/out
