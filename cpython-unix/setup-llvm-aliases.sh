#!/bin/sh
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -e

# Build scripts and configure probes also invoke the standard binutils names.
for tool in ar ranlib nm strip objdump objcopy readelf size strings addr2line; do
    test -x "/tools/llvm/bin/llvm-$tool"
    ln -sf "llvm-$tool" "/tools/llvm/bin/$tool"
done
test -x /tools/llvm/bin/llvm-cxxfilt
ln -sf llvm-cxxfilt /tools/llvm/bin/c++filt
test -x /tools/llvm/bin/ld.lld
ln -sf ld.lld /tools/llvm/bin/ld
