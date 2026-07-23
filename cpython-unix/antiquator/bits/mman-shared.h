#include_next <bits/mman-shared.h>

#define weaken(sym) extern __typeof(sym) sym __attribute__((weak))

#ifdef _GNU_SOURCE
weaken(memfd_create);
#endif
