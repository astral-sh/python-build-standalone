#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Validate a relocated native macOS artifact using the installed Apple SDK.
set -euo pipefail
if [[ $(uname -s) != Darwin || $# != 1 ]]; then
    echo "Usage (on macOS): $0 /path/to/extracted/llvm" >&2
    exit 1
fi
toolchain=$(cd "$1" && pwd)
sdk="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
fixture=$(mktemp -d)
trap 'rm -rf "${fixture}"' EXIT
cd "${fixture}"

"${toolchain}/bin/clang" --version
"${toolchain}/bin/ld64.lld" --version
"${toolchain}/bin/llvm-bolt" --version

cat > hello.c <<'C'
#include <stdio.h>
int main(void) {
    puts("C OK");
    return 0;
}
C
cat > hello.cpp <<'CPP'
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <vector>
int main() {
    std::vector<int> values{1, 2, 3};
    try {
        throw std::runtime_error("C++ exceptions OK");
    } catch (const std::exception& e) {
        std::cout << e.what() << '\n';
    }
    return std::accumulate(values.begin(), values.end(), 0) != 6;
}
CPP

"${toolchain}/bin/clang" -isysroot "${sdk}" -mmacosx-version-min=11.0 hello.c -o hello-c
./hello-c
"${toolchain}/bin/clang++" -isysroot "${sdk}" -mmacosx-version-min=11.0 \
    -std=c++17 hello.cpp -o hello-cxx
./hello-cxx
"${toolchain}/bin/clang++" -isysroot "${sdk}" -mmacosx-version-min=11.0 \
    -std=c++17 -flto=thin -fuse-ld=lld hello.cpp -o hello-lto
./hello-lto
"${toolchain}/bin/clang" -isysroot "${sdk}" -mmacosx-version-min=11.0 \
    -fprofile-instr-generate hello.c -o hello-instrumented
LLVM_PROFILE_FILE=hello.profraw ./hello-instrumented
"${toolchain}/bin/llvm-profdata" merge -o hello.profdata hello.profraw
"${toolchain}/bin/clang" -isysroot "${sdk}" -mmacosx-version-min=11.0 \
    -O2 -flto=full -fprofile-instr-use=hello.profdata hello.c -o hello-pgo
./hello-pgo
echo 'Native macOS toolchain smoke tests passed.'
