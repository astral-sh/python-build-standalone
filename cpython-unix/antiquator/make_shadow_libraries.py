#!/usr/bin/env -S uv run --no-project
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "tree-sitter",
#     "tree-sitter-c",
# ]
# ///

from collections.abc import Generator
import dataclasses
import os
import pathlib
import sys
import textwrap
from typing import Self

import tree_sitter
import tree_sitter_c

C_LANGUAGE = tree_sitter.Language(tree_sitter_c.language())
PARSER = tree_sitter.Parser(C_LANGUAGE)


class QueryDataclass:
    def __init_subclass__(cls, query, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._QUERY = tree_sitter.Query(C_LANGUAGE, query)

    @classmethod
    def matches(cls, node: tree_sitter.Node) -> Generator[Self]:
        qc = tree_sitter.QueryCursor(cls._QUERY)
        fields = dataclasses.fields(cls)
        for _, m in qc.matches(node):
            yield cls(*(m[f.name][0].text.decode() for f in fields))

class GlibcVersion:
    def __init__(self, ver: str):
        self._ver = ver
        if not ver.startswith("GLIBC_"):
            self._components = None
            return
        self._components = tuple(int(i) for i in ver.removeprefix("GLIBC_").split("_"))
        if self._components < (2, 2, 5):  # TODO x86-64 only
            self._components = (2, 2, 5)

    def __lt__(self, other: Self):
        if self._components and other._components:
            return self._components < other._components
        else:
            return str(self) < str(other)

    def __str__(self):
        if self._components:
            return "GLIBC_" + ".".join(str(i) for i in self._components)
        else:
            return self._ver

    def __repr__(self):
        return f"<GlibcVersion {self} (originally {self._ver})>"


@dataclasses.dataclass
class Symbol(
    QueryDataclass,
    query="""(call_expression
        function: (identifier) @macro
        (#any-of? @macro "versioned_symbol" "compat_symbol")
        arguments: (argument_list
            (identifier) @lib
            (identifier) @local
            (identifier) @symbol
            (identifier) @version
        )
    )""",
):
    macro: str
    lib: str
    local: str
    symbol: str
    version: str


@dataclasses.dataclass
class Weaken(
    QueryDataclass,
    query="""(call_expression
        function: (identifier) @macro
        (#eq? @macro "weaken")
        arguments: (argument_list
            (identifier) @symbol
        )
    )""",
):
    symbol: str


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make_shadow_libraries.py path/to/glibc/source path/to/output")
    glibc = pathlib.Path(sys.argv[1])
    output = pathlib.Path(sys.argv[2])

    versioned = {}
    compat = []

    for file in glibc.glob("**/*.c"):
        t = PARSER.parse(file.read_bytes())
        for symbol in Symbol.matches(t.root_node):
            match symbol:
                case Symbol(macro="compat_symbol", lib="libc", symbol="dlinfo", version="GLIBC_2_3_3"):
                    # typo in glibc source
                    symbol.lib = "libdl"
                case Symbol(symbol="__libdl_version_placeholder"):
                    # used to populate the stub libdl, not relevant to us
                    continue
                case Symbol(version="GLIBC_PRIVATE"):
                    # not relevant to us, hopefully
                    continue

            if symbol.macro == "versioned_symbol":
                versioned[symbol.local] = symbol
            else:
                print(symbol)
                compat.append(symbol)

    versioned["__real_libc_start_main"] = None
    compat.append(Symbol("compat_symbol", "libc", "__real_libc_start_main", "real_libc_start_main", "GLIBC_2_2_5"))

    # glibc before 2.30 doesn't properly handle weak versioned symbols,
    # so we have to de-version them. (Note the order of where
    # _dl_lookup_symbol_x in elf/dl-lookup.c handles STB_WEAK vs.
    # versioned symbols.)
    weak_unversioned = set()
    for file in output.glob("**/*.h"):
        t = PARSER.parse(file.read_bytes())
        for weaken in Weaken.matches(t.root_node):
            weak_unversioned.add(weaken.symbol)

    libs: dict[str, dict[str, GlibcVersion]] = {}
    for symbol in compat:
        if symbol.local in versioned:
            lib = libs.setdefault(symbol.lib, {})
            name = symbol.symbol
            version = GlibcVersion(symbol.version)
            if name in lib:
                # min? max? max up to glibc 2.17 or whatever?
                lib[name] = min(lib[name], version)
            else:
                lib[name] = version

    for lib, symbols in libs.items():
        with open(output / f"{lib}_placeholder.c", "w") as f:
            print("__attribute__((", file=f)
            for symbol, version in symbols.items():
                print(f'symver("{symbol}@@{version}"),', file=f)
            print(")) void placeholder(void) {}", file=f)
            if lib == "libc":
                for symbol in weak_unversioned:
                    print(f"void {symbol}(void) {{}}", file=f)
        with open(output / f"{lib}_placeholder.versions", "w") as f:
            for version in set(str(version) for version in symbols.values()):
                print(f"{version} {{}};", file=f)
