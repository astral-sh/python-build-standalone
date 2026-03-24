#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "openssl-${OPENSSL_3_5_VERSION}.tar.gz"

pushd "openssl-${OPENSSL_3_5_VERSION}"

# Fedora and RHEL patch OpenSSL to selectively disallow SHA1 signatures via the
# 'rh-allow-sha1-signatures' configuration entry.
# Patch OpenSSL so that this key is allowed in configuration files but has no effect.
# For details see: https://github.com/astral-sh/python-build-standalone/issues/999
if [[ "$TARGET_TRIPLE" =~ "linux" ]]; then
	patch -p1 << 'EOF'
diff --git a/crypto/evp/evp_cnf.c b/crypto/evp/evp_cnf.c
index 184bab9..7dc8037 100644
--- a/crypto/evp/evp_cnf.c
+++ b/crypto/evp/evp_cnf.c
@@ -51,6 +51,13 @@ static int alg_module_init(CONF_IMODULE *md, const CONF *cnf)
                 ERR_raise(ERR_LIB_EVP, EVP_R_SET_DEFAULT_PROPERTY_FAILURE);
                 return 0;
             }
+        } else if (strcmp(oval->name, "rh-allow-sha1-signatures") == 0) {
+            int m;
+
+            /* Detailed error already reported. */
+            if (!X509V3_get_value_bool(oval, &m))
+                return 0;
+
         } else if (strcmp(oval->name, "default_properties") == 0) {
             if (!evp_set_default_properties_int(NCONF_get0_libctx((CONF *)cnf),
                     oval->value, 0, 0)) {
EOF
fi

# Otherwise it gets set to /tools/deps/ssl by default.
case "${TARGET_TRIPLE}" in
    *apple*)
        EXTRA_FLAGS="--openssldir=/private/etc/ssl"
        ;;
    *)
        EXTRA_FLAGS="--openssldir=/etc/ssl"
        ;;
esac

# musl is missing support for various primitives.
# TODO disable secure memory is a bit scary. We should look into a proper
# workaround.
if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="${EXTRA_FLAGS} no-async -DOPENSSL_NO_ASYNC -D__STDC_NO_ATOMICS__=1 no-engine -DOPENSSL_NO_SECURE_MEMORY"
fi

# The -arch cflags confuse Configure. And OpenSSL adds them anyway.
# Strip them.
EXTRA_TARGET_CFLAGS=${EXTRA_TARGET_CFLAGS/\-arch arm64/}
EXTRA_TARGET_CFLAGS=${EXTRA_TARGET_CFLAGS/\-arch x86_64/}

EXTRA_FLAGS="${EXTRA_FLAGS} ${EXTRA_TARGET_CFLAGS}"

/usr/bin/perl ./Configure \
  --prefix=/tools/deps \
  --libdir=lib \
  "${OPENSSL_TARGET}" \
  no-legacy \
  no-shared \
  no-tests \
  ${EXTRA_FLAGS}

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install_sw install_ssldirs DESTDIR="${ROOT}/out"
