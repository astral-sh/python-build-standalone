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

tar -xf bzip2-${BZIP2_VERSION}.tar.gz

pushd bzip2-${BZIP2_VERSION}

make -j ${NUM_CPUS} install \
    AR=${AR} \
    CC="${CC}" \
    CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" \
    LDFLAGS="${EXTRA_TARGET_LDFLAGS}" \
    PREFIX=${ROOT}/out/tools/deps
