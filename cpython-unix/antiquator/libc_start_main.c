#include <stdio.h>

extern int __libc_csu_init(int argc, char **argv, char **envp);

#define LIBC_START_MAIN_ARGS \
                 int (*main) (int, char **, char **), \
                 int argc, char **argv, \
                 __typeof (main) init, \
                 void (*fini) (void), \
                 void (*rtld_fini) (void), void *stack_end

extern int real_libc_start_main(LIBC_START_MAIN_ARGS);

// The static linker needs to find this under the name
// __libc_start_main, so that crt1.o calls this one instead of the real
// one in libc. But after we rename real_libc_start_main with patchelf
// to __libc_start_main, the dynamic linker needs to _not_ find this one
// and instead find the real one. To accomplish this, we give it a
// non-default symbol version that does not match the symbol version
// that we actually want.
__attribute__((symver("__libc_start_main@ANTIQUATOR_SHIM")))
int __libc_start_main(LIBC_START_MAIN_ARGS) {
	return real_libc_start_main(main, argc, argv, __libc_csu_init, fini, rtld_fini, stack_end);
}

