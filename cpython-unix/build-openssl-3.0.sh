#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf openssl-${OPENSSL_3_0_VERSION}.tar.gz

pushd openssl-${OPENSSL_3_0_VERSION}

# Otherwise it gets set to /tools/deps/ssl by default.
case "${TARGET_TRIPLE}" in
    *apple*)
        OPENSSL_DIR=/private/etc/ssl
        ;;
    *)
        OPENSSL_DIR=/etc/ssl
        ;;
esac
EXTRA_FLAGS="--openssldir=${OPENSSL_DIR}"
EXTRA_INSTALL_FLAGS=""

# musl is missing support for various primitives.
# TODO disable secure memory is a bit scary. We should look into a proper
# workaround.
if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="${EXTRA_FLAGS} no-async -DOPENSSL_NO_ASYNC -D__STDC_NO_ATOMICS__=1 no-engine -DOPENSSL_NO_SECURE_MEMORY"
else
    EXTRA_INSTALL_FLAGS="install_fips"
    EXTRA_FLAGS="${EXTRA_FLAGS} enable-fips"
fi

# The -arch cflags confuse Configure. And OpenSSL adds them anyway.
# Strip them.
EXTRA_TARGET_CFLAGS=${EXTRA_TARGET_CFLAGS/\-arch arm64/}
EXTRA_TARGET_CFLAGS=${EXTRA_TARGET_CFLAGS/\-arch x86_64/}

# With -fvisibility=hidden, OSSL_provider_init symbol is not exported in fips module preventing it from loaded
# OSSL_provider_init is supposed to be `extern` so it should not happen but I can't find a more targeted solution
# at the moment.
EXTRA_TARGET_CFLAGS=${EXTRA_TARGET_CFLAGS//-fvisibility=hidden/}
EXTRA_FLAGS="${EXTRA_FLAGS} ${EXTRA_TARGET_CFLAGS}"

/usr/bin/perl ./Configure \
  --prefix=/tools/deps \
  --libdir=lib \
  ${OPENSSL_TARGET} \
  no-legacy \
  no-shared \
  no-tests \
  ${EXTRA_FLAGS}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install_sw install_ssldirs ${EXTRA_INSTALL_FLAGS} DESTDIR=${ROOT}/out

if [ -f ${ROOT}/out${OPENSSL_DIR}/fipsmodule.cnf  ]; then
    # install_fips does not use DESTDIR. we need to copy it so it gets added to the archive.
    cp ${ROOT}/out${OPENSSL_DIR}/fipsmodule.cnf ${ROOT}/out/tools/deps/fipsmodule.cnf
fi
