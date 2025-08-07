#!/usr/bin/env python3
#
# usage: repad_install_name.py <filename>
# Rewrites /usr/lib/././././libpython.dylib to /usr/lib/libpython.dylib,
# keeping NUL padding in the load command.
#
# Useful references:
#   `xcrun --show-sdk-platform-path`/Developer/usr/include/mach-o/loader.h
#   https://en.wikipedia.org/wiki/Mach-O (some factual inaccuracies)

import re
import struct
import sys


def rewrite(f):
    f.seek(0, 0)
    mach_header = f.read(28)
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags = struct.unpack(
        "=7I", mach_header
    )
    if magic == 0xFEEDFACE:
        pass
    elif magic == 0xFEEDFACF:
        _reserved = f.read(4)
    elif magic in (0xCEFAEDFE, 0xCFFAEDFE):
        raise RuntimeError("Wrong-endian Mach-O file")
    else:
        raise RuntimeError("Not a Mach-O file?")

    loadstart = f.tell()

    for i in range(ncmds):
        load_command_header = f.read(8)
        cmd, cmdsize = struct.unpack("=2I", load_command_header)
        load_command_body = f.read(cmdsize - 8)
        if cmd == 0xD:  # LC_ID_DYLIB
            name_offset, timestamp, current_version, compatbility_version = (
                struct.unpack_from("=4I", load_command_body)
            )
            bufsize = cmdsize - 24
            if name_offset != 24 or bufsize <= 0:
                raise RuntimeError("Malformed load command")
            install_name = load_command_body[16:].rstrip(b"\0")
            new_install_name, replacements = re.subn(b"/(\./)+", b"/", install_name)
            if replacements > 0:
                print(f"Rewriting install_name to {new_install_name}")
                f.seek(-bufsize, 1)
                f.write(new_install_name.ljust(bufsize, b"\0"))

    if f.tell() != loadstart + sizeofcmds:
        raise RuntimeError("Unexpected end of load commands, is file corrupt?")


if __name__ == "__main__":
    with open(sys.argv[1], "r+b") as f:
        rewrite(f)
