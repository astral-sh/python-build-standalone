#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p build
docker buildx build --platform linux/amd64 --load \
    --iidfile build/image-x86_64.txt .

docker run --platform linux/amd64 --network none \
    --cidfile build/container-x86_64.txt \
    --mount "type=bind,source=${PWD}/scripts,target=/scripts,readonly" \
    -e PARALLEL="${PARALLEL:-16}" \
    -e SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --pretty=%ct)}" \
    "$(cat build/image-x86_64.txt)" bash -euc '
        cp /scripts/gcc-build-linux.sh /scripts/llvm-build-linux.sh \
            /scripts/llvm-assemble-toolchain.sh /build/
        bash /build/gcc-build-linux.sh
        bash /build/llvm-build-linux.sh
        bash /build/llvm-assemble-toolchain.sh
    '

cid=$(cat build/container-x86_64.txt)
docker cp "${cid}:/build/llvm-gnu_only-x86_64-unknown-linux-gnu.tar.zst" build/
docker rm "${cid}"
rm build/container-x86_64.txt
