#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

# Force linking to static libraries from our dependencies.
# TODO(geofft): This is copied from build-cpython.sh. Really this should
# be done at the end of the build of each dependency, rather than before
# the build of each consumer.
find ${TOOLS_PATH}/deps -name '*.so*' -exec rm {} \;

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

tar -xf tcl${TCL_VERSION}-src.tar.gz
pushd tcl${TCL_VERSION}

EXTRA_CONFIGURE=

if [ -n "${STATIC}" ]; then
	patch -p1 << 'EOF'
diff --git a/unix/Makefile.in b/unix/Makefile.in
--- a/unix/Makefile.in
+++ b/unix/Makefile.in
@@ -2062,7 +2062,7 @@ configure-packages:
 			  $$i/configure --with-tcl8 --with-tcl=../.. \
 			      --with-tclinclude=$(GENERIC_DIR) \
 			      $(PKG_CFG_ARGS) --libdir=$(PACKAGE_DIR) \
-			      --enable-shared; ) || exit $$?; \
+			      --enable-shared=no; ) || exit $$?; \
 		    fi; \
 		    mkdir -p $(PKG_DIR)/$$pkg; \
 		    if [ ! -f $(PKG_DIR)/$$pkg/Makefile ] ; then \
@@ -2070,7 +2070,7 @@ configure-packages:
 			  $$i/configure --with-tcl=../.. \
 			      --with-tclinclude=$(GENERIC_DIR) \
 			      $(PKG_CFG_ARGS) --libdir=$(PACKAGE_DIR) \
-			      --enable-shared; ) || exit $$?; \
+			      --enable-shared=no; ) || exit $$?; \
 		    fi; \
 		fi; \
 	    fi; \
EOF
fi

# Disable the use of fts64_* functions on the 32-bit armv7 platform as these
# functions are not available in glibc 2.17
if [[ ${TARGET_TRIPLE} = armv7* ]]; then
    EXTRA_CONFIGURE="${EXTRA_CONFIGURE} tcl_cv_flag__file_offset_bits=no"
fi

# musl does not include queue.h
# https://wiki.musl-libc.org/faq#Q:-Why-is-%3Ccode%3Esys/queue.h%3C/code%3E-not-included?
# It is a self contained header file, use a copy from the container.
# https://core.tcl-lang.org/tcl/tktview/3ff2d724d03ba7d6edb8
if [ "${CC}" = "musl-clang" ]; then
    cp /usr/include/$(uname -m)-linux-gnu/sys/queue.h /tools/host/include/sys
fi

# Remove packages we don't care about and can pull in unwanted symbols.
rm -rf pkgs/sqlite* pkgs/tdbc*

pushd unix

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include"
LDFLAGS="${EXTRA_TARGET_CFLAGS} -L${TOOLS_PATH}/deps/lib"
if [[ "${PYBUILD_PLATFORM}" != macos* ]]; then
    LDFLAGS="${LDFLAGS} -Wl,--exclude-libs,ALL"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" LDFLAGS="${LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --enable-shared"${STATIC:+=no}" \
    --enable-threads \
    --disable-zipfs \
    ${EXTRA_CONFIGURE}

make -j ${NUM_CPUS} DYLIB_INSTALL_DIR=@rpath
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out DYLIB_INSTALL_DIR=@rpath
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

if [ -n "${STATIC}" ]; then
    # For some reason libtcl*.a have weird permissions. Fix that.
    chmod 644 ${ROOT}/out/tools/deps/lib/libtcl*.a
fi
