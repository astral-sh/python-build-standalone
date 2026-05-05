#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf "patchelf-${PATCHELF_VERSION}.tar.bz2"

pushd "patchelf-${PATCHELF_VERSION}"

# TODO: Drop this patch once patchelf is updated to 0.14.0 or newer,
# which includes native LoongArch64 support.
# See: https://github.com/astral-sh/python-build-standalone/issues/1106
if [[ "${TARGET_TRIPLE}" = loongarch64* ]]; then
    patch -p1 << 'EOF'
diff --git a/src/patchelf.cc b/src/patchelf.cc
index 2b7ec8b9..06f41c6f 100644
--- a/src/patchelf.cc
+++ b/src/patchelf.cc
@@ -57,6 +57,10 @@ static int forcedPageSize = DEFAULT_PAGESIZE;
 static int forcedPageSize = -1;
 #endif
 
+#ifndef EM_LOONGARCH
+#define EM_LOONGARCH    258
+#endif
+
 using FileContents = std::shared_ptr<std::vector<unsigned char>>;
 
 #define ElfFileParams class Elf_Ehdr, class Elf_Phdr, class Elf_Shdr, class Elf_Addr, class Elf_Off, class Elf_Dyn, class Elf_Sym, class Elf_Verneed, class Elf_Versym
@@ -460,6 +464,7 @@ unsigned int ElfFile<ElfFileParamNames>::getPageSize() const
       case EM_PPC64:
       case EM_AARCH64:
       case EM_TILEGX:
+      case EM_LOONGARCH:
         return 0x10000;
       default:
         return 0x1000;
EOF
fi

CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_HOST_CFLAGS} -fPIC" \
    ./configure \
        --build="${BUILD_TRIPLE}" \
        --host="${TARGET_TRIPLE}" \
        --prefix=/tools/host

make -j "$(nproc)"
make -j "$(nproc)" install DESTDIR="${ROOT}/out"

# Update DT_NEEDED to use the host toolchain's shared libraries, otherwise
# the defaults of the OS may be used, which would be too old. We run the
# patched binary afterwards to verify it works without LD_LIBRARY_PATH
# modification.
if [ -d "/tools/${TOOLCHAIN}/lib" ]; then
    LD_LIBRARY_PATH=/tools/${TOOLCHAIN}/lib src/patchelf --replace-needed libstdc++.so.6 "/tools/${TOOLCHAIN}/lib/libstdc++.so.6" "${ROOT}/out/tools/host/bin/patchelf"
    LD_LIBRARY_PATH=/tools/${TOOLCHAIN}/lib src/patchelf --replace-needed libgcc_s.so.1 "/tools/${TOOLCHAIN}/lib/libgcc_s.so.1" "${ROOT}/out/tools/host/bin/patchelf"
fi

"${ROOT}/out/tools/host/bin/patchelf" --version
