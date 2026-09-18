#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Package LLVM with the GCC headers and runtime libraries.
set -euo pipefail
umask 022

arch=$(uname -m)
GCC_MAJOR=${GCC_VERSION%%.*}
export PATH=/usr/local/bin:/usr/bin:/bin LC_ALL=C.UTF-8 TZ=UTC

# Remove large LLVM binaries that are unnecessary for the toolchain.
rm -f /build/llvm-install/bin/c-index-test
rm -f /build/llvm-install/bin/llvm-exegesis

mkdir -p /build/llvm-package/llvm
cd /build/llvm-package
cp -a /build/llvm-install/. llvm/

# Copy GCC's versioned support files, C++ headers, and runtime libraries.
cp -a /build/out-support/lib/gcc llvm/lib/
cp -a /build/out-support/include/c++ llvm/include/
cp -a /build/out-support/lib64/. "llvm/lib/gcc/${arch}-linux-gnu/${GCC_MAJOR}/"

# Let LLVM's relative runtime paths find the bundled GCC shared libraries.
for library in libstdc++.so.6 libgcc_s.so.1 libatomic.so.1; do
    ln -s "gcc/${arch}-linux-gnu/${GCC_MAJOR}/${library}" "llvm/lib/${library}"
done

# Keep archive ordering, ownership, timestamps, and compression deterministic.
mtime=$(date -u -d "@${SOURCE_DATE_EPOCH}" '+%Y-%m-%d 00:00:00')
tar --format=gnu --sort=name --owner=root:0 --group=root:0 --mtime="${mtime}" \
    -cf - llvm | zstd -T"${PARALLEL}" -18 -o "/build/llvm-gnu_only-${arch}-unknown-linux-gnu.tar.zst"
