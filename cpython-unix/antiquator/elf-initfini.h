// Somewhat confusing name - this means "this code is going into
// libc_nonshared.a", the library of static code that is linked when
// you're using libc.so. So effectively it means you _are_ targeting a
// shared link and not a static link.
#define LIBC_NONSHARED 1

#define ELF_INITFINI 1

#define attribute_hidden __attribute__((visibility("hidden")))
