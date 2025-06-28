ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-unix
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=
SPACE := $(subst ,, )

ALL_PYTHON_VERSIONS := 3.9 3.10 3.11 3.12 3.13 3.14

ifndef PYBUILD_TARGET_TRIPLE
    $(error PYBUILD_TARGET_TRIPLE not defined)
endif

ifndef PYBUILD_BUILD_OPTIONS
    $(error PYBUILD_BUILD_OPTIONS not defined)
endif

ifndef PYBUILD_HOST_PLATFORM
    $(error PYBUILD_HOST_PLATFORM not defined)
endif

ifndef PYBUILD_PYTHON_SOURCE
    $(error PYBUILD_PYTHON_SOURCE not defined)
endif

ifndef PYBUILD_PYTHON_VERSION
    $(error PYBUILD_PYTHON_VERSION not defined)
endif

PYTHON_MAJOR_VERSION := $(subst $(SPACE),.,$(wordlist 1,2,$(subst .,$(SPACE),$(PYBUILD_PYTHON_VERSION))))

TARGET_TRIPLE := $(PYBUILD_TARGET_TRIPLE)
HOST_PLATFORM := $(PYBUILD_HOST_PLATFORM)
PACKAGE_SUFFIX := $(TARGET_TRIPLE)-$(PYBUILD_BUILD_OPTIONS)

RUN_BUILD = $(BUILD) \
    --host-platform $(HOST_PLATFORM) \
    --target-triple $(TARGET_TRIPLE) \
    --options $(PYBUILD_BUILD_OPTIONS) \
    --python-source $(PYBUILD_PYTHON_SOURCE) \
    --dest-archive $@ \
    $(NULL)

ifdef PYBUILD_MUSL
    PLATFORM := $(PLATFORM)-musl
endif

# Always write out settings files.
$(shell $(RUN_BUILD) placeholder_archive makefiles)
include $(OUTDIR)/Makefile.$(HOST_PLATFORM).$(TARGET_TRIPLE)
include $(OUTDIR)/versions/VERSION.*

# Always write out expanded Dockerfiles.
$(shell $(RUN_BUILD) placeholder_archive dockerfiles)

BASE_TOOLCHAIN_DEPENDS := \
    $(if $(NEED_BINUTILS),$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar) \
    $(OUTDIR)/$(CLANG_FILENAME) \
    $(NULL)

TOOLCHAIN_DEPENDS := \
    $(BASE_TOOLCHAIN_DEPENDS) \
    $(if $(NEED_MUSL),$(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar) \
    $(NULL)

PYTHON_DEP_DEPENDS := \
    $(OUTDIR)/targets/$(TARGET_TRIPLE) \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-$(DOCKER_IMAGE_BUILD).$(HOST_PLATFORM).tar) \
    $(TOOLCHAIN_DEPENDS) \
    $(NULL)

HOST_PYTHON_DEPENDS := $(OUTDIR)/cpython-$(PYTHON_MAJOR_VERSION)-$(CPYTHON_$(PYTHON_MAJOR_VERSION)_VERSION)-$(HOST_PLATFORM).tar

default: $(OUTDIR)/cpython-$(CPYTHON_$(PYTHON_MAJOR_VERSION)_VERSION)-$(PACKAGE_SUFFIX).tar

ifndef PYBUILD_NO_DOCKER
$(OUTDIR)/image-%.$(HOST_PLATFORM).tar: $(OUTDIR)/%.Dockerfile
	$(RUN_BUILD) --toolchain image-$*
endif

$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar: $(HERE)/build-binutils.sh
	$(RUN_BUILD) --toolchain --docker-image $(DOCKER_IMAGE_GCC) binutils

$(OUTDIR)/$(CLANG_FILENAME):
	$(RUN_BUILD) --toolchain clang --target-triple $(TARGET_TRIPLE)

$(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar: $(BASE_TOOLCHAIN_DEPENDS) $(HERE)/build-musl.sh
	$(RUN_BUILD) --toolchain musl --docker-image $(DOCKER_IMAGE_GCC)

ifeq ($(HOST_PLATFORM),linux_x86_64)
    TOOLCHAIN_TARGET := $(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar
else
    TOOLCHAIN_TARGET :=
endif

empty:

toolchain: $(TOOLCHAIN_TARGET)

toolchain-image-%: $(OUTDIR)/%.Dockerfile
	$(RUN_BUILD) --toolchain image-$*

AUTOCONF_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-autoconf.sh \
    $(OUTDIR)/m4-$(M4_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/autoconf-$(AUTOCONF_VERSION)-$(PACKAGE_SUFFIX).tar: $(AUTOCONF_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) autoconf

$(OUTDIR)/bdb-$(BDB_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bdb.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) bdb

$(OUTDIR)/bzip2-$(BZIP2_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bzip2.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) bzip2

$(OUTDIR)/expat-$(EXPAT_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-expat.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) expat

$(OUTDIR)/libffi-3.3-$(LIBFFI_3.3_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libffi-3.3.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libffi-3.3

$(OUTDIR)/libffi-$(LIBFFI_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libffi.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libffi

$(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libpthread-stubs.sh $(OUTDIR)/image-$(DOCKER_IMAGE_BUILD).$(HOST_PLATFORM).tar
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libpthread-stubs

LIBX11_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libX11.sh \
    $(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBX11_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libX11

LIBXAU_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libXau.sh \
    $(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBXAU_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libXau

LIBXCB_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HOST_PYTHON_DEPENDS) \
    $(HERE)/build-libxcb.sh \
    $(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBXCB_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) --python-host-version $(PYBUILD_PYTHON_VERSION) libxcb

$(OUTDIR)/m4-$(M4_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-m4.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) m4

$(OUTDIR)/mpdecimal-$(MPDECIMAL_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-mpdecimal.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) mpdecimal

$(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-ncurses.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) ncurses

$(OUTDIR)/openssl-1.1-$(OPENSSL_1.1_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-openssl-1.1.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) openssl-1.1

$(OUTDIR)/openssl-3.0-$(OPENSSL_3.0_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-openssl-3.0.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) openssl-3.0

LIBEDIT_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(HERE)/build-libedit.sh \
    $(NULL)

$(OUTDIR)/libedit-$(LIBEDIT_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBEDIT_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) libedit

$(OUTDIR)/patchelf-$(PATCHELF_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-patchelf.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) patchelf

$(OUTDIR)/sqlite-$(SQLITE_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-sqlite.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) sqlite

$(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-tcl.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) tcl

TIX_DEPENDS = \
    $(HERE)/build-tix.sh \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/tk-$(TK_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_LIBX11),$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(NULL)

$(OUTDIR)/tix-$(TIX_VERSION)-$(PACKAGE_SUFFIX).tar: $(TIX_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) tix

TK_DEPENDS = \
    $(HOST_PYTHON_DEPENDS) \
    $(HERE)/build-tk.sh \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_LIBX11),$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(NULL)

$(OUTDIR)/tk-$(TK_VERSION)-$(PACKAGE_SUFFIX).tar: $(TK_DEPENDS)
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) --python-host-version $(PYBUILD_PYTHON_VERSION) tk

$(OUTDIR)/uuid-$(UUID_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-uuid.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) uuid

$(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-x11-util-macros.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) x11-util-macros

$(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HOST_PYTHON_DEPENDS) $(HERE)/build-xcb-proto.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) --python-host-version $(PYBUILD_PYTHON_VERSION) xcb-proto

$(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xorgproto.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) xorgproto

$(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xtrans.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) xtrans

$(OUTDIR)/xz-$(XZ_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xz.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) xz

$(OUTDIR)/zlib-$(ZLIB_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-zlib.sh
	$(RUN_BUILD) --docker-image $(DOCKER_IMAGE_BUILD) zlib

PYTHON_HOST_DEPENDS := \
  $(PYTHON_DEP_DEPENDS) \
  $(HERE)/build-cpython-host.sh \
  $(OUTDIR)/autoconf-$(AUTOCONF_VERSION)-$(PACKAGE_SUFFIX).tar \
  $(OUTDIR)/m4-$(M4_VERSION)-$(PACKAGE_SUFFIX).tar \
  $(NULL)

# Each X.Y Python version has its own set of variables and targets. This independent
# definition allows multiple Python versions to be built using the same Makefile
# invocation.
define python_version_template
PYTHON_DEPENDS_$(1) := \
    $$(PYTHON_SUPPORT_FILES) \
    $$(OUTDIR)/versions/VERSION.pip \
    $$(OUTDIR)/versions/VERSION.setuptools \
    $$(OUTDIR)/cpython-$(1)-$$(CPYTHON_$(1)_VERSION)-$$(HOST_PLATFORM).tar \
    $$(if$$(NEED_AUTOCONF),$$(OUTDIR)/autoconf-$$(AUTOCONF_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_BDB),$$(OUTDIR)/bdb-$$(BDB_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_BZIP2),$$(OUTDIR)/bzip2-$$(BZIP2_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_EXPAT),$$(OUTDIR)/expat-$$(EXPAT_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_LIBEDIT),$$(OUTDIR)/libedit-$$(LIBEDIT_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_LIBFFI_3_3),$$(OUTDIR)/libffi-3.3-$$(LIBFFI_3.3_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_LIBFFI),$$(OUTDIR)/libffi-$$(LIBFFI_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_m4),$$(OUTDIR)/m4-$$(M4_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_MPDECIMAL),$$(OUTDIR)/mpdecimal-$$(MPDECIMAL_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_NCURSES),$$(OUTDIR)/ncurses-$$(NCURSES_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_OPENSSL_1_1),$$(OUTDIR)/openssl-1.1-$$(OPENSSL_1.1_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_OPENSSL_3_0),$$(OUTDIR)/openssl-3.0-$$(OPENSSL_3.0_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_PATCHELF),$$(OUTDIR)/patchelf-$$(PATCHELF_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_SQLITE),$$(OUTDIR)/sqlite-$$(SQLITE_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_TCL),$$(OUTDIR)/tcl-$$(TCL_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_TK),$$(OUTDIR)/tk-$$(TK_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_TIX),$$(OUTDIR)/tix-$$(TIX_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_UUID),$$(OUTDIR)/uuid-$$(UUID_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_XZ),$$(OUTDIR)/xz-$$(XZ_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(if $$(NEED_ZLIB),$$(OUTDIR)/zlib-$$(ZLIB_VERSION)-$$(PACKAGE_SUFFIX).tar) \
    $$(NULL)

ALL_PYTHON_DEPENDS_$(1) = \
    $$(PYTHON_DEP_DEPENDS) \
    $$(HERE)/build-cpython.sh \
    $$(PYTHON_DEPENDS_$(1)) \
    $$(NULL)

$$(OUTDIR)/cpython-$(1)-$$(CPYTHON_$(1)_VERSION)-$$(HOST_PLATFORM).tar: $$(PYTHON_HOST_DEPENDS)
	$$(RUN_BUILD) --docker-image $$(DOCKER_IMAGE_BUILD) cpython-$(1)-host

$$(OUTDIR)/cpython-$$(CPYTHON_$(1)_VERSION)-$$(PACKAGE_SUFFIX).tar: $$(ALL_PYTHON_DEPENDS_$(1))
	$$(RUN_BUILD) --docker-image $$(DOCKER_IMAGE_BUILD) cpython-$(1)
endef

$(foreach local_version,$(ALL_PYTHON_VERSIONS),$(eval $(call python_version_template,$(local_version))))
