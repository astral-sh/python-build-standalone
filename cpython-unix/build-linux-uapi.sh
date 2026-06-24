#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

archives=("${ROOT}"/linux-libc-dev_*.deb)
if [[ ${#archives[@]} -ne 1 || ! -f "${archives[0]}" ]]; then
    echo "expected exactly one linux-libc-dev package"
    exit 1
fi

mkdir -p "${ROOT}/linux-uapi-package" "${ROOT}/out/tools/deps/linux-uapi"
pushd "${ROOT}/linux-uapi-package"
ar x "${archives[0]}" data.tar.xz
tar -xf data.tar.xz -C "${ROOT}/out/tools/deps/linux-uapi"
popd
