#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "libffi-${LIBFFI_VERSION}.tar.gz"

pushd "libffi-${LIBFFI_VERSION}"

# libffi uses linux/limits.h and linux/types.h for PATH_MAX. 
# Use the standard header so musl builds do not require Linux headers.
patch -p1 <<'EOF'
diff --git a/src/tramp.c b/src/tramp.c
--- a/src/tramp.c
+++ b/src/tramp.c
@@ -53,9 +53,3 @@
 #include <tramp.h>
-#ifdef __linux__
-#include <linux/limits.h>
-#include <linux/types.h>
-#endif
-#ifdef __CYGWIN__
 #include <limits.h>
-#endif
 #endif
EOF

EXTRA_CONFIGURE=

# mkostemp() was introduced in macOS 10.10 and libffi doesn't have
# runtime guards for it. So ban the symbol when targeting old macOS.
if [ "${APPLE_MIN_DEPLOYMENT_TARGET}" = "10.9" ]; then
    EXTRA_CONFIGURE="${EXTRA_CONFIGURE} ac_cv_func_mkostemp=no"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build="${BUILD_TRIPLE}" \
    --host="${TARGET_TRIPLE}" \
    --prefix=/tools/deps \
    --disable-shared \
    ${EXTRA_CONFIGURE}

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"
