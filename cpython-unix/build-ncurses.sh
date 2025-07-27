#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf ncurses-${NCURSES_VERSION}.tar.gz

# When cross-compiling, ncurses uses the host `tic` to build the terminfo
# database. But our build environment's `tic` is too old to process this
# ncurses version. Our workaround is to build ncurses for the host when
# cross-compiling then make its `tic` available to the target ncurses
# build.
if [[ -n "${CROSS_COMPILING}" && "${PYBUILD_PLATFORM}" != macos* ]]; then
  echo "building host ncurses to provide modern tic for cross-compile"

  pushd ncurses-${NCURSES_VERSION}

  CC="${HOST_CC}" ./configure \
    --prefix=${TOOLS_PATH}/host \
    --without-cxx \
    --without-tests \
    --without-manpages \
    --enable-widec \
    --disable-db-install \
    --enable-symlinks
  make -j ${NUM_CPUS}
  make -j ${NUM_CPUS} install

  popd

  # Nuke and re-pave the source directory.
  rm -rf ncurses-${NCURSES_VERSION}
  tar -xf ncurses-${NCURSES_VERSION}.tar.gz
fi

pushd ncurses-${NCURSES_VERSION}

# `make install` will strip installed programs (like tic) by default. This is
# fine. However, cross-compiles can run into issues where `strip` doesn't
# recognize the target architecture. We could fix this by overriding strip.
# But we don't care about the installed binaries, so we simply disable
# stripping of the binaries.
# --enable-symlinks is needed to force use of symbolic links in the terminfo
# database. By default hardlinks are used, which are wonky to tar up. Be sure
# this is set on the host native `tic` build above, as it is the entity writing
# symlinks!
CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/tools/deps
    --without-cxx
    --without-tests
    --without-manpages
    --disable-stripping
    --enable-widec
    --enable-symlinks
    "

# ncurses wants --with-build-cc when cross-compiling. But it insists on CC
# and this value not being equal, even though using the same binary with
# different compiler flags is doable!
if [[ -n "${CROSS_COMPILING}" && "${PYBUILD_PLATFORM}" != macos* ]]; then
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-cc=$(which "${HOST_CC}")"
fi

# The terminfo database exists as a set of standalone files. The absolute
# paths to these files need to be hardcoded into the binary at build time.
#
# Since our final distributions are "relocatable," the absolute path of the
# terminfo database can't be known at build time: there needs to be something
# that sniffs for well-known directories and attempts to locate it. Ideally
# that could find the terminfo database that we ship!
#
# All is not lost, however.
#
# On macOS, the system terminfo database location is well known: /usr/share/terminfo.
#
# On Linux, common distributions tend to place the terminfo database in only a
# few well-known locations. We define default search paths that overlap with
# Debian and RedHat distros. This often results in at least a partially working
# terminfo lookup in most Linux environments.
#
# configure appears to use --with-default-terminfo-dir for both a) where to
# install the terminfo database to b) default TERMINFO value compiled into the
# binary. So we provide a suitable runtime value and then move files at install
# time.

if [[ "${PYBUILD_PLATFORM}" = macos* ]]; then
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS}
    --datadir=/usr/share
    --sysconfdir=/etc
    --sharedstatedir=/usr/com
    --with-default-terminfo-dir=/usr/share/terminfo
    --with-terminfo-dirs=/usr/share/terminfo
  "
else
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS}
    --datadir=/tools/deps/usr/share
    --sysconfdir=/tools/deps/etc
    --sharedstatedir=/tools/deps/usr/com
    --with-default-terminfo-dir=/usr/share/terminfo
    --with-terminfo-dirs=/etc/terminfo:/lib/terminfo:/usr/share/terminfo
  "
fi

mkdir -p ${ROOT}/out/usr/lib

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure ${CONFIGURE_FLAGS}
make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out

mv ${ROOT}/out/usr/share/terminfo ${ROOT}/out/tools/deps/usr/share/
