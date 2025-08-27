#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

export ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:${TOOLS_PATH}/deps/bin:$PATH

# autoconf has some paths hardcoded into scripts. These paths just work in
# the containerized build environment. But from macOS the paths are wrong.
# Explicitly point to the proper path via environment variable overrides.
export AUTOCONF=${TOOLS_PATH}/host/bin/autoconf
export AUTOHEADER=${TOOLS_PATH}/host/bin/autoheader
export AUTOM4TE=${TOOLS_PATH}/host/bin/autom4te
export autom4te_perllibdir=${TOOLS_PATH}/host/share/autoconf
export AC_MACRODIR=${TOOLS_PATH}/host/share/autoconf
export M4=${TOOLS_PATH}/host/bin/m4
export trailer_m4=${TOOLS_PATH}/host/share/autoconf/autoconf/trailer.m4

# The share/autoconf/autom4te.cfg file also hard-codes some paths. Rewrite
# those to the real tools path.
if [[ "${PYBUILD_PLATFORM}" = macos* ]]; then
  sed_args="-i '' -e"
else
  sed_args="-i"
fi

sed ${sed_args} "s|/tools/host|${TOOLS_PATH}/host|g" ${TOOLS_PATH}/host/share/autoconf/autom4te.cfg

tar -xf Python-${PYTHON_VERSION}.tar.xz

pushd "Python-${PYTHON_VERSION}"

# Clang 13 actually prints something with --print-multiarch, confusing CPython's
# configure. This is reported as https://bugs.python.org/issue45405. We nerf the
# check since we know what we're doing.
if [ "${CC}" = "clang" ]; then
  if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_13}" ]; then
    patch -p1 -i ${ROOT}/patch-disable-multiarch-13.patch
  else
    patch -p1 -i ${ROOT}/patch-disable-multiarch.patch
  fi
elif [ "${CC}" = "musl-clang" ]; then
  # Similarly, this is a problem for musl Clang on Python 3.13+
  if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_13}" ]; then
    patch -p1 -i ${ROOT}/patch-disable-multiarch-13.patch
  fi
fi

autoconf

# When cross-compiling, we need to build a host Python that has working zlib
# and ctypes extensions, otherwise various things fail. (`make install` fails
# without zlib and setuptools / pip used by target install fail due to missing
# ctypes.)
#
# On Apple, the dependencies are present in the Apple SDK and missing extensions
# are built properly by setup.py. However, on other platforms, we need to teach
# the host build system where to find things.
#
# Adding /usr paths on Linux is a bit funky. This is a side-effect or our
# custom Clang purposefully omitting default system search paths to help
# prevent unwanted dependencies from sneaking in.
case "${BUILD_TRIPLE}" in
  x86_64-unknown-linux-gnu)
    EXTRA_HOST_CFLAGS="${EXTRA_HOST_CFLAGS} -I/usr/include/x86_64-linux-gnu"
    EXTRA_HOST_CPPFLAGS="${EXTRA_HOST_CPPFLAGS} -I/usr/include/x86_64-linux-gnu"
    EXTRA_HOST_LDFLAGS="${EXTRA_HOST_LDFLAGS} -L/usr/lib/x86_64-linux-gnu"
    ;;
  aarch64-unknown-linux-gnu)
    EXTRA_HOST_CFLAGS="${EXTRA_HOST_CFLAGS} -I/usr/include/aarch64-linux-gnu"
    EXTRA_HOST_CPPFLAGS="${EXTRA_HOST_CPPFLAGS} -I/usr/include/aarch64-linux-gnu"
    EXTRA_HOST_LDFLAGS="${EXTRA_HOST_LDFLAGS} -L/usr/lib/aarch64-linux-gnu"
    ;;
  *)
    ;;
esac

EXTRA_CONFIGURE_FLAGS=

# We may not have a usable libraries to build against. Forcefully disable extensions
# that may not build.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
    for m in _hashlib _ssl; do
      EXTRA_CONFIGURE_FLAGS="${EXTRA_CONFIGURE_FLAGS} py_cv_module_${m}=n/a"
    done
  fi

CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS}" CPPFLAGS="${EXTRA_HOST_CFLAGS}" LDFLAGS="${EXTRA_HOST_LDFLAGS}" ./configure \
  --prefix /tools/host \
  --without-ensurepip \
  ${EXTRA_CONFIGURE_FLAGS}

# Ideally we'd do `make install` here and be done with it. But there's a race
# condition in CPython's build system related to directory creation that gets
# tickled when we do this. https://github.com/python/cpython/issues/109796.
make -j "${NUM_CPUS}"
make -j sharedinstall DESTDIR=${ROOT}/out
make -j install DESTDIR=${ROOT}/out

popd
