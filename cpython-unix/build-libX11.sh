#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf libX11-${LIBX11_VERSION}.tar.gz
pushd libX11-${LIBX11_VERSION}

patch -p1 << 'EOF'
diff --git a/configure b/configure
--- a/configure
+++ b/configure
@@ -19557,8 +19557,6 @@ else
 		RAWCPPFLAGS="-undef -ansi"
 		{ $as_echo "$as_me:${as_lineno-$LINENO}: result: yes, with -ansi" >&5
 $as_echo "yes, with -ansi" >&6; }
-	else
-		as_fn_error $? "${RAWCPP} defines unix with or without -undef.  I don't know what to do." "$LINENO" 5
 	fi
 fi
 rm -f conftest.$ac_ext
@@ -19578,8 +19576,6 @@ else
 		RAWCPPFLAGS="${RAWCPPFLAGS} -traditional"
 		{ $as_echo "$as_me:${as_lineno-$LINENO}: result: yes" >&5
 $as_echo "yes" >&6; }
-	else
-		as_fn_error $? "${RAWCPP} does not preserve whitespace with or without -traditional.  I don't know what to do." "$LINENO" 5
 	fi
 fi
 rm -f conftest.$ac_ext
EOF

if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="--disable-shared"
fi

# configure doesn't support cross-compiling in malloc(0) returns null test.
# So we have to force a value.
if [ -n "${CROSS_COMPILING}" ]; then
  case "${TARGET_TRIPLE}" in
    aarch64-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    armv7-unknown-linux-gnueabi)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    armv7-unknown-linux-gnueabihf)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    i686-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    mips-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    mipsel-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    mips64el-unknown-linux-gnuabi64)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    ppc64le-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    riscv64-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    s390x-unknown-linux-gnu)
      EXTRA_FLAGS="${EXTRA_FLAGS} --enable-malloc0returnsnull"
      ;;
    *)
      echo "cross-compiling but malloc(0) override not set; failures possible"
      ;;
  esac
fi

# CC_FOR_BUILD is here because configure doesn't look for `clang` when
# cross-compiling. So we force it.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I/tools/deps/include" \
  CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I/tools/deps/include" \
  LDFLAGS="${EXTRA_TARGET_LDFLAGS}" \
  CC_FOR_BUILD="${HOST_CC}" \
  CFLAGS_FOR_BUILD="-I/tools/deps/include" \
  CPPFLAGS_FOR_BUILD="-I/tools/deps/include" \
  ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-silent-rules \
    ${EXTRA_FLAGS}

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out
