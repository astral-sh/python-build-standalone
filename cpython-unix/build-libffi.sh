#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf libffi-${LIBFFI_VERSION}.tar.gz

pushd libffi-${LIBFFI_VERSION}

# Patches needed to fix compilation on aarch64. Will presumably be in libffi
# 3.4.7 or 3.5.

# Commit f64141ee3f9e455a060bd09e9ab72b6c94653d7c.
patch -p1 <<'EOF'
diff --git a/src/aarch64/sysv.S b/src/aarch64/sysv.S
index fdd0e8b..60cfa50 100644
--- a/src/aarch64/sysv.S
+++ b/src/aarch64/sysv.S
@@ -68,7 +68,7 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
 #define BTI_J hint #36
 /*
  * The ELF Notes section needs to indicate if BTI is supported, as the first ELF loaded that doesn't
- * declare this support disables it for the whole process.
+ * declare this support disables it for memory region containing the loaded library.
  */
 # define GNU_PROPERTY_AARCH64_BTI (1 << 0)         /* Has Branch Target Identification */
 	.text
@@ -527,6 +527,7 @@ L(do_closure):
 #if defined(FFI_EXEC_STATIC_TRAMP)
 	.align 4
 CNAME(ffi_closure_SYSV_V_alt):
+	BTI_C
 	/* See the comments above trampoline_code_table. */
 	ldr	x17, [sp, #8]			/* Load closure in x17 */
 	add	sp, sp, #16			/* Restore the stack */
@@ -541,6 +542,7 @@ CNAME(ffi_closure_SYSV_V_alt):

 	.align 4
 CNAME(ffi_closure_SYSV_alt):
+	BTI_C
 	/* See the comments above trampoline_code_table. */
 	ldr	x17, [sp, #8]			/* Load closure in x17 */
 	add	sp, sp, #16			/* Restore the stack */
diff --git a/testsuite/Makefile.am b/testsuite/Makefile.am
index d286cf7..6ba98e1 100644
--- a/testsuite/Makefile.am
+++ b/testsuite/Makefile.am
@@ -8,7 +8,7 @@ CLEANFILES = *.exe core* *.log *.sum

 EXTRA_DIST = config/default.exp emscripten/build.sh emscripten/conftest.py \
 	emscripten/node-tests.sh emscripten/test.html emscripten/test_libffi.py \
-  emscripten/build-tests.sh lib/libffi.exp lib/target-libpath.exp \
+	emscripten/build-tests.sh lib/libffi.exp lib/target-libpath.exp \
 	lib/wrapper.exp libffi.bhaible/Makefile libffi.bhaible/README \
 	libffi.bhaible/alignof.h libffi.bhaible/bhaible.exp libffi.bhaible/test-call.c \
 	libffi.bhaible/test-callback.c libffi.bhaible/testcases.c libffi.call/align_mixed.c \
EOF

# Commit 45d284f2d066cc3a080c5be88e51b4d934349797.
patch -p1 <<'EOF'
diff --git a/configure.ac b/configure.ac
index 816bfd6..b35a999 100644
--- a/configure.ac
+++ b/configure.ac
@@ -189,17 +189,17 @@ AC_CACHE_CHECK([whether compiler supports pointer authentication],
    AC_COMPILE_IFELSE([AC_LANG_PROGRAM([[]], [[
 #ifdef __clang__
 # if __has_feature(ptrauth_calls)
-#  define HAVE_PTRAUTH 1
+#  define HAVE_ARM64E_PTRAUTH 1
 # endif
 #endif

-#ifndef HAVE_PTRAUTH
+#ifndef HAVE_ARM64E_PTRAUTH
 # error Pointer authentication not supported
 #endif
 		   ]])],[libffi_cv_as_ptrauth=yes],[libffi_cv_as_ptrauth=no])
 ])
 if test "x$libffi_cv_as_ptrauth" = xyes; then
-    AC_DEFINE(HAVE_PTRAUTH, 1,
+    AC_DEFINE(HAVE_ARM64E_PTRAUTH, 1,
 	      [Define if your compiler supports pointer authentication.])
 fi

diff --git a/include/ffi_cfi.h b/include/ffi_cfi.h
index f4c292d..8565663 100644
--- a/include/ffi_cfi.h
+++ b/include/ffi_cfi.h
@@ -49,6 +49,7 @@
 # define cfi_personality(enc, exp)	.cfi_personality enc, exp
 # define cfi_lsda(enc, exp)		.cfi_lsda enc, exp
 # define cfi_escape(...)		.cfi_escape __VA_ARGS__
+# define cfi_window_save		.cfi_window_save

 #else

@@ -71,6 +72,7 @@
 # define cfi_personality(enc, exp)
 # define cfi_lsda(enc, exp)
 # define cfi_escape(...)
+# define cfi_window_save

 #endif /* HAVE_AS_CFI_PSEUDO_OP */
 #endif /* FFI_CFI_H */
diff --git a/src/aarch64/ffi.c b/src/aarch64/ffi.c
index b13738e..964934d 100644
--- a/src/aarch64/ffi.c
+++ b/src/aarch64/ffi.c
@@ -63,7 +63,7 @@ struct call_context
 #if FFI_EXEC_TRAMPOLINE_TABLE

 #ifdef __MACH__
-#ifdef HAVE_PTRAUTH
+#ifdef HAVE_ARM64E_PTRAUTH
 #include <ptrauth.h>
 #endif
 #include <mach/vm_param.h>
@@ -877,7 +877,7 @@ ffi_prep_closure_loc (ffi_closure *closure,

 #if FFI_EXEC_TRAMPOLINE_TABLE
 # ifdef __MACH__
-#  ifdef HAVE_PTRAUTH
+#  ifdef HAVE_ARM64E_PTRAUTH
   codeloc = ptrauth_auth_data(codeloc, ptrauth_key_function_pointer, 0);
 #  endif
   void **config = (void **)((uint8_t *)codeloc - PAGE_MAX_SIZE);
diff --git a/src/aarch64/internal.h b/src/aarch64/internal.h
index b5d102b..c39f9cb 100644
--- a/src/aarch64/internal.h
+++ b/src/aarch64/internal.h
@@ -81,20 +81,62 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
 /* Helpers for writing assembly compatible with arm ptr auth */
 #ifdef LIBFFI_ASM

-#ifdef HAVE_PTRAUTH
-#define SIGN_LR pacibsp
-#define SIGN_LR_WITH_REG(x) pacib lr, x
-#define AUTH_LR_AND_RET retab
-#define AUTH_LR_WITH_REG(x) autib lr, x
-#define BRANCH_AND_LINK_TO_REG blraaz
-#define BRANCH_TO_REG braaz
-#else
-#define SIGN_LR
-#define SIGN_LR_WITH_REG(x)
-#define AUTH_LR_AND_RET ret
-#define AUTH_LR_WITH_REG(x)
-#define BRANCH_AND_LINK_TO_REG blr
-#define BRANCH_TO_REG br
-#endif
-
-#endif
+  #if defined(HAVE_ARM64E_PTRAUTH)
+  /* ARM64E ABI For Darwin */
+  #define SIGN_LR pacibsp
+  #define SIGN_LR_WITH_REG(x) pacib lr, x
+  #define AUTH_LR_AND_RET retab
+  #define AUTH_LR_WITH_REG(x) autib lr, x
+  #define BRANCH_AND_LINK_TO_REG blraaz
+  #define BRANCH_TO_REG braaz
+  #define PAC_CFI_WINDOW_SAVE
+  /* Linux PAC Support */
+  #elif defined(__ARM_FEATURE_PAC_DEFAULT)
+    #define GNU_PROPERTY_AARCH64_POINTER_AUTH (1 << 1)
+    #define PAC_CFI_WINDOW_SAVE cfi_window_save
+    #define TMP_REG x9
+    #define BRANCH_TO_REG br
+    #define BRANCH_AND_LINK_TO_REG blr
+	#define SIGN_LR_LINUX_ONLY SIGN_LR
+    /* Which key to sign with? */
+    #if (__ARM_FEATURE_PAC_DEFAULT & 1) == 1
+      /* Signed with A-key */
+      #define SIGN_LR            hint #25  /* paciasp */
+      #define AUTH_LR            hint #29  /* autiasp */
+    #else
+      /* Signed with B-key */
+      #define SIGN_LR            hint #27  /* pacibsp */
+      #define AUTH_LR            hint #31  /* autibsp */
+    #endif /* __ARM_FEATURE_PAC_DEFAULT */
+    #define AUTH_LR_WITH_REG(x) _auth_lr_with_reg x
+.macro _auth_lr_with_reg modifier
+    mov TMP_REG, sp
+    mov sp, \modifier
+    AUTH_LR
+    mov sp, TMP_REG
+.endm
+  #define SIGN_LR_WITH_REG(x) _sign_lr_with_reg x
+.macro _sign_lr_with_reg modifier
+    mov TMP_REG, sp
+    mov sp, \modifier
+    SIGN_LR
+    mov sp, TMP_REG
+.endm
+  #define AUTH_LR_AND_RET _auth_lr_and_ret modifier
+.macro _auth_lr_and_ret modifier
+    AUTH_LR
+    ret
+.endm
+  #undef TMP_REG
+
+  /* No Pointer Auth */
+  #else
+    #define SIGN_LR
+    #define SIGN_LR_WITH_REG(x)
+    #define AUTH_LR_AND_RET ret
+    #define AUTH_LR_WITH_REG(x)
+    #define BRANCH_AND_LINK_TO_REG blr
+    #define BRANCH_TO_REG br
+    #define PAC_CFI_WINDOW_SAVE
+  #endif /* HAVE_ARM64E_PTRAUTH */
+#endif /* LIBFFI_ASM */
diff --git a/src/aarch64/sysv.S b/src/aarch64/sysv.S
index 60cfa50..6a9a561 100644
--- a/src/aarch64/sysv.S
+++ b/src/aarch64/sysv.S
@@ -92,27 +92,27 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
 	cfi_startproc
 CNAME(ffi_call_SYSV):
 	BTI_C
-	/* Sign the lr with x1 since that is where it will be stored */
+	PAC_CFI_WINDOW_SAVE
+	/* Sign the lr with x1 since that is the CFA which is the modifer used in auth instructions */
 	SIGN_LR_WITH_REG(x1)

-	/* Use a stack frame allocated by our caller.  */
-#if defined(HAVE_PTRAUTH) && defined(__APPLE__)
+#if defined(HAVE_ARM64E_PTRAUTH) && defined(__APPLE__)
 	/* darwin's libunwind assumes that the cfa is the sp and that's the data
 	 * used to sign the lr.  In order to allow unwinding through this
 	 * function it is necessary to point the cfa at the signing register.
 	 */
 	cfi_def_cfa(x1, 0);
-#else
-	cfi_def_cfa(x1, 40);
 #endif
+	/* Use a stack frame allocated by our caller.  */
 	stp	x29, x30, [x1]
+	cfi_def_cfa_register(x1)
+	cfi_rel_offset (x29, 0)
+	cfi_rel_offset (x30, 8)
 	mov	x9, sp
 	str	x9, [x1, #32]
 	mov	x29, x1
-	mov	sp, x0
 	cfi_def_cfa_register(x29)
-	cfi_rel_offset (x29, 0)
-	cfi_rel_offset (x30, 8)
+	mov	sp, x0

 	mov	x9, x2			/* save fn */
 	mov	x8, x3			/* install structure return */
@@ -326,6 +326,7 @@ CNAME(ffi_closure_SYSV_V):
 	cfi_startproc
 	BTI_C
 	SIGN_LR
+	PAC_CFI_WINDOW_SAVE
 	stp     x29, x30, [sp, #-ffi_closure_SYSV_FS]!
 	cfi_adjust_cfa_offset (ffi_closure_SYSV_FS)
 	cfi_rel_offset (x29, 0)
@@ -351,6 +352,7 @@ CNAME(ffi_closure_SYSV_V):
 CNAME(ffi_closure_SYSV):
 	BTI_C
 	SIGN_LR
+	PAC_CFI_WINDOW_SAVE
 	stp     x29, x30, [sp, #-ffi_closure_SYSV_FS]!
 	cfi_adjust_cfa_offset (ffi_closure_SYSV_FS)
 	cfi_rel_offset (x29, 0)
@@ -648,6 +650,8 @@ CNAME(ffi_go_closure_SYSV_V):
 	cfi_startproc
 CNAME(ffi_go_closure_SYSV):
 	BTI_C
+	SIGN_LR_LINUX_ONLY
+	PAC_CFI_WINDOW_SAVE
 	stp     x29, x30, [sp, #-ffi_closure_SYSV_FS]!
 	cfi_adjust_cfa_offset (ffi_closure_SYSV_FS)
 	cfi_rel_offset (x29, 0)
diff --git a/src/closures.c b/src/closures.c
index 67a94a8..02cf78f 100644
--- a/src/closures.c
+++ b/src/closures.c
@@ -164,7 +164,7 @@ ffi_tramp_is_present (__attribute__((unused)) void *ptr)

 #include <mach/mach.h>
 #include <pthread.h>
-#ifdef HAVE_PTRAUTH
+#ifdef HAVE_ARM64E_PTRAUTH
 #include <ptrauth.h>
 #endif
 #include <stdio.h>
@@ -223,7 +223,7 @@ ffi_trampoline_table_alloc (void)
   /* Remap the trampoline table on top of the placeholder page */
   trampoline_page = config_page + PAGE_MAX_SIZE;

-#ifdef HAVE_PTRAUTH
+#ifdef HAVE_ARM64E_PTRAUTH
   trampoline_page_template = (vm_address_t)(uintptr_t)ptrauth_auth_data((void *)&ffi_closure_trampoline_table_page, ptrauth_key_function_pointer, 0);
 #else
   trampoline_page_template = (vm_address_t)&ffi_closure_trampoline_table_page;
@@ -268,7 +268,7 @@ ffi_trampoline_table_alloc (void)
       ffi_trampoline_table_entry *entry = &table->free_list_pool[i];
       entry->trampoline =
 	(void *) (trampoline_page + (i * FFI_TRAMPOLINE_SIZE));
-#ifdef HAVE_PTRAUTH
+#ifdef HAVE_ARM64E_PTRAUTH
       entry->trampoline = ptrauth_sign_unauthenticated(entry->trampoline, ptrauth_key_function_pointer, 0);
 #endif

EOF

# Commit 9c9e8368e49804c4f7c35ac9f0d7c1d0d533308b.
patch -p1 <<'EOF'
diff --git a/src/aarch64/internal.h b/src/aarch64/internal.h
index c39f9cb..50fa5c1 100644
--- a/src/aarch64/internal.h
+++ b/src/aarch64/internal.h
@@ -88,6 +88,7 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
   #define AUTH_LR_AND_RET retab
   #define AUTH_LR_WITH_REG(x) autib lr, x
   #define BRANCH_AND_LINK_TO_REG blraaz
+  #define SIGN_LR_LINUX_ONLY
   #define BRANCH_TO_REG braaz
   #define PAC_CFI_WINDOW_SAVE
   /* Linux PAC Support */
@@ -136,6 +137,7 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
     #define AUTH_LR_AND_RET ret
     #define AUTH_LR_WITH_REG(x)
     #define BRANCH_AND_LINK_TO_REG blr
+    #define SIGN_LR_LINUX_ONLY
     #define BRANCH_TO_REG br
     #define PAC_CFI_WINDOW_SAVE
   #endif /* HAVE_ARM64E_PTRAUTH */
EOF

# Commit 8308bed5b2423878aa20d7884a99cf2e30b8daf7.
patch -p1 <<'EOF'
diff --git a/src/aarch64/sysv.S b/src/aarch64/sysv.S
index 6a9a561..e83bc65 100644
--- a/src/aarch64/sysv.S
+++ b/src/aarch64/sysv.S
@@ -89,8 +89,8 @@ SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.  */
    x5 closure
 */

-	cfi_startproc
 CNAME(ffi_call_SYSV):
+	cfi_startproc
 	BTI_C
 	PAC_CFI_WINDOW_SAVE
 	/* Sign the lr with x1 since that is the CFA which is the modifer used in auth instructions */
@@ -348,8 +348,8 @@ CNAME(ffi_closure_SYSV_V):
 #endif

 	.align	4
-	cfi_startproc
 CNAME(ffi_closure_SYSV):
+	cfi_startproc
 	BTI_C
 	SIGN_LR
 	PAC_CFI_WINDOW_SAVE
@@ -647,8 +647,8 @@ CNAME(ffi_go_closure_SYSV_V):
 #endif

 	.align	4
-	cfi_startproc
 CNAME(ffi_go_closure_SYSV):
+	cfi_startproc
 	BTI_C
 	SIGN_LR_LINUX_ONLY
 	PAC_CFI_WINDOW_SAVE
EOF

EXTRA_CONFIGURE=

# mkostemp() was introduced in macOS 10.10 and libffi doesn't have
# runtime guards for it. So ban the symbol when targeting old macOS.
if [ "${APPLE_MIN_DEPLOYMENT_TARGET}" = "10.9" ]; then
    EXTRA_CONFIGURE="${EXTRA_CONFIGURE} ac_cv_func_mkostemp=no"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    ${EXTRA_CONFIGURE}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
