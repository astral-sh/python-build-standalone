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
	if echo "${TARGET_TRIPLE}" | grep -q -- "-unknown-linux-musl"; then
		# tcl will use an internal implementation of certain POSIX function when
		# cross-compiling. The implementation of strtoul create multiple definitions
		# when linked against the static musl libc. Exclude the internal implementation.
		EXTRA_CONFIGURE="${EXTRA_CONFIGURE} tcl_cv_strtoul_unbroken=ok"
	fi

	patch -p1 << 'EOF'
diff --git a/unix/Makefile.in b/unix/Makefile.in
--- a/unix/Makefile.in
+++ b/unix/Makefile.in
@@ -1813,7 +1813,7 @@ configure-packages:
 			  $$i/configure --with-tcl=../.. \
 			      --with-tclinclude=$(GENERIC_DIR) \
 			      $(PKG_CFG_ARGS) --libdir=$(PACKAGE_DIR) \
-			      --enable-shared --enable-threads; ) || exit $$?; \
+			      --enable-shared=no --enable-threads; ) || exit $$?; \
 		    fi; \
 		fi; \
 	    fi; \
EOF
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
    ${EXTRA_CONFIGURE}

make -j ${NUM_CPUS} DYLIB_INSTALL_DIR=@rpath
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out DYLIB_INSTALL_DIR=@rpath
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

if [ -n "${STATIC}" ]; then
    # For some reason libtcl*.a have weird permissions. Fix that.
    chmod 644 ${ROOT}/out/tools/deps/lib/libtcl*.a
fi
