#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Build and run smoke tests in a clean old Debian reference image.
# Usage: validate-linux.sh <x86_64|aarch64> <distribution> [builder-image]
set -euo pipefail
umask 022

arch=${1:?Usage: validate-linux.sh <x86_64|aarch64> <distribution> [builder-image]}
case "${arch}" in
    x86_64)
        platform=linux/amd64
        glibc_version=2.19
        smoke_image=debian@sha256:32ad5050caffb2c7e969dac873bce2c370015c2256ff984b70c1c08b3a2816a0
        ;;
    aarch64)
        platform=linux/arm64
        glibc_version=2.24
        smoke_image=debian@sha256:c5c5200ff1e9c73ffbf188b4a67eb1c91531b644856b4aefe86a58d2f0cb05be
        ;;
    *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;;
esac

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
distribution=${2:?Usage: validate-linux.sh <x86_64|aarch64> <distribution> [builder-image]}
if [[ ! -f ${distribution} && ! -d ${distribution} ]]; then
    echo "Missing toolchain distribution: ${distribution}" >&2
    exit 1
fi
distribution=$(cd -- "$(dirname -- "${distribution}")" && pwd)/$(basename -- "${distribution}")
builder_image=${3:-$(cat "${script_dir}/build/image-${arch}.txt")}

if ! docker image inspect "${smoke_image}" > /dev/null 2>&1; then
    docker pull --platform "${platform}" "${smoke_image}"
fi
volume=$(docker volume create --label pbs-toolchain-validation)
trap 'docker volume rm "${volume}" > /dev/null' EXIT

# Prepare the distribution and old C headers/startup files on a Linux filesystem.
echo "Preparing ${distribution}"
docker run --rm --platform "${platform}" --network none --read-only --user 0:0 \
    --mount "type=bind,source=${distribution},target=/distribution,readonly" \
    --mount "type=volume,source=${volume},target=/validation" \
    "${builder_image}" bash -euc '
        if [[ -d /distribution ]]; then
            cp -a /distribution /validation/llvm
        else
            tar --zstd -xpf /distribution -C /validation
        fi
        cp -a "${SYSROOT}" /validation/sysroot
    '

# Compile and run every sample in the reference image, using its standard loader.
echo "Running ${arch} smoke tests on glibc ${glibc_version}"
docker run --rm --interactive --platform "${platform}" --network none --read-only \
    --tmpfs /tmp:rw,exec,size=128m \
    --mount "type=volume,source=${volume},target=/validation,readonly" \
    "${smoke_image}" bash -euo pipefail -s -- "${arch}" "${glibc_version}" <<'SH'
test "$(uname -m)" = "$1"
test "$(getconf GNU_LIBC_VERSION)" = "glibc $2"
TOOLCHAIN_DIR=/validation/llvm
SYSROOT=/validation/sysroot
export PATH="${TOOLCHAIN_DIR}/bin:/usr/bin:/bin" LC_ALL=C.UTF-8 TZ=UTC
cd "$(mktemp -d)"

cat > smoke.c <<'C'
#include <stdio.h>
int main(void) { return puts("C smoke test passed") < 0; }
C
cat > smoke.cc <<'CPP'
#include <atomic>
#include <stdexcept>
#include <string>
int main() {
    std::atomic<unsigned __int128> value{42};
    try { throw std::runtime_error("smoke test"); }
    catch (const std::exception &e) {
        return value.load() == 42 && std::string(e.what()) == "smoke test" ? 0 : 1;
    }
}
CPP

echo 'Building and running C'
clang --sysroot="${SYSROOT}" -fuse-ld=lld smoke.c -o c
./c
echo 'Building and running C++ exceptions and atomics with shared runtimes'
clang++ --sysroot="${SYSROOT}" -fuse-ld=lld smoke.cc -latomic \
    -Wl,-rpath,"${TOOLCHAIN_DIR}/lib" -o cxx
./cxx
echo 'Building and running C++ exceptions and atomics with static C++ runtimes'
clang++ --sysroot="${SYSROOT}" -fuse-ld=lld -static-libstdc++ -static-libgcc \
    smoke.cc -latomic -Wl,-rpath,"${TOOLCHAIN_DIR}/lib" -o cxx-static
./cxx-static
echo 'Building and running AddressSanitizer'
clang --sysroot="${SYSROOT}" -fuse-ld=lld -fsanitize=address smoke.c -o asan
if ! ./asan 2> asan.stderr || [[ -s asan.stderr ]]; then
    cat asan.stderr >&2
    exit 1
fi
echo 'Building and running LTO with lld'
clang --sysroot="${SYSROOT}" -fuse-ld=lld -flto smoke.c -o lto
./lto
SH
echo "Smoke tests passed: ${distribution}"
