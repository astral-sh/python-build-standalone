#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p build
docker buildx build --platform linux/arm64 --load \
    --iidfile build/image-aarch64.txt .

docker run --platform linux/arm64 --network none \
    --cidfile build/container-aarch64.txt \
    --mount "type=bind,source=${PWD}/scripts,target=/scripts,readonly" \
    -e PARALLEL="${PARALLEL:-16}" \
    -e SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git log -1 --pretty=%ct)}" \
    "$(cat build/image-aarch64.txt)" bash -euc '
        cp /scripts/gcc-build-linux.sh /scripts/llvm-build-linux.sh \
            /scripts/llvm-assemble-toolchain.sh /build/
        bash /build/gcc-build-linux.sh
        bash /build/llvm-build-linux.sh
        bash /build/llvm-assemble-toolchain.sh
    '

cid=$(cat build/container-aarch64.txt)
docker cp "${cid}:/build/llvm-gnu_only-aarch64-unknown-linux-gnu.tar.zst" build/
docker rm "${cid}"
rm build/container-aarch64.txt
