GLIBC ?= glibc-2.39/

LIBS := libanl libc libdl libm libpthread libresolv librt libutil
HELPERS := elf-init.o libc_start_main.o

all: ${LIBS:=_placeholder.so} libantiquator_helpers.a(${HELPERS})

%.so: %.c %.versions
	${CC} -fPIC -shared -o $@ $< -Wl,--version-script,$*.versions

${LIBS:=_placeholder.c} ${LIBS:=_placeholder.versions} &: make_shadow_libraries.py ${GLIBC}
	./make_shadow_libraries.py ${GLIBC} .

clean:
	-${RM} ${LIBS:=_placeholder.so} ${LIBS:=_placeholder.c} ${LIBS:=._placeholder.versions} libc_start_main.o

elf-init.o: CFLAGS += -I.

glibc-%/:
	apt-get source glibc

.PHONY: all clean
.SECONDARY:
