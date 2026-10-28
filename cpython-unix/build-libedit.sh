#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf "libedit-${LIBEDIT_VERSION}.tar.gz"

pushd "libedit-${LIBEDIT_VERSION}"

# libedit probes for tgetent in ncurses, but we build the wide-character library.
patch -p1 <<'EOF'
--- a/configure.ac
+++ b/configure.ac
@@ -48,5 +48,5 @@
-AC_CHECK_LIB(ncurses, tgetent,,
+AC_CHECK_LIB(ncursesw, tgetent,,
   [AC_CHECK_LIB(curses, tgetent,,
     [AC_CHECK_LIB(termcap, tgetent,,
       [AC_CHECK_LIB(tinfo, tgetent,,
-        [AC_MSG_ERROR([libncurses, libcurses, libtermcap or libtinfo is required!])]
+        [AC_MSG_ERROR([libncursesw, libcurses, libtermcap or libtinfo is required!])]
EOF
# Keep make from regenerating the release's Automake files after this edit.
touch -r aclocal.m4 configure.ac
autoconf

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"
ldflags="${EXTRA_TARGET_LDFLAGS} -L${TOOLS_PATH}/deps/lib"

# musl doesn't define __STDC_ISO_10646__, so work around that.
if [ "${CC}" = "musl-clang" ]; then
    cflags="${cflags} -D__STDC_ISO_10646__=201103L"
fi

CFLAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="${ldflags}" \
    ./configure \
        --build="${BUILD_TRIPLE}" \
        --host="${TARGET_TRIPLE}" \
        --prefix=/tools/deps \
        --disable-shared

make -j "${NUM_CPUS}"
make -j "${NUM_CPUS}" install DESTDIR="${ROOT}/out"

# Alias readline/{history.h, readline.h} for readline compatibility.
if [ -e "${ROOT}/out/tools/deps/include" ]; then
    mkdir "${ROOT}/out/tools/deps/include/readline"
    ln -s ../editline/readline.h "${ROOT}/out/tools/deps/include/readline/readline.h"
    ln -s ../editline/readline.h "${ROOT}/out/tools/deps/include/readline/history.h"
fi
