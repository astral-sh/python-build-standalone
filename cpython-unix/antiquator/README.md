Antiquator - Use a newer glibc to build for older glibc versions
===

This is a set of utilities to enable building binaries using a newer
glibc that can run on older glibc versions: if a symbol exists in an
older version, prefer that implementation, and if a symbol does not
exist in an older version, enable weak linking against it (runtime value
is NULL if not found).

First, run `make` to build shadow libraries from glibc sources.  If you
already have a glibc checkout, you can use `make GLIBC=/path/to/glibc`.
This should be as new as your compile-time glibc; newer will probably
work fine but is probably not helpful, since you won't pick up any
symbols from it.

Then set the `antiquator` environment variable to this directory. (This
needs to be an exported environment variable.)

Finally, use `gcc -specs ${antiquator}/gcc.spec` or `clang --config
${antiquator}/clang.config` for compiling and linking (e.g. add those options
to `CFLAGS` and `LDFLAGS`).

The clang implementation uses `-fuse-ld` internally; to pick the actual
linker, you can use `-Wl,-fuse-ld=...`.

Requirements
---

You need a relatively recent toolchain (at least binutils 2.35+) and
patchelf.

lld seems to not work as a linker. This might be an lld bug. (bfd ld and
gold both seem to work.)

Credits
---

elf-init.c is taken from glibc 2.33, the last version that had it. It is
unmodified from the version that was in glibc and used under the license
exception stated in the file.
