// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::{json::*, macho::*},
    anyhow::{anyhow, Context, Result},
    clap::ArgMatches,
    normalize_path::NormalizePath,
    object::{
        elf::{
            FileHeader32, FileHeader64, ET_DYN, ET_EXEC, STB_GLOBAL, STB_WEAK, STV_DEFAULT,
            STV_HIDDEN,
        },
        macho::{MachHeader32, MachHeader64, MH_OBJECT, MH_TWOLEVEL},
        read::{
            elf::{Dyn, FileHeader, SectionHeader, Sym},
            macho::{LoadCommandVariant, MachHeader, Nlist},
            pe::{ImageNtHeaders, PeFile, PeFile32, PeFile64},
        },
        Endianness, FileKind, Object, SectionIndex, SymbolScope,
    },
    once_cell::sync::Lazy,
    std::{
        collections::{BTreeSet, HashMap},
        convert::TryInto,
        io::Read,
        iter::FromIterator,
        path::{Path, PathBuf},
    },
};

const RECOGNIZED_TRIPLES: &[&str] = &[
    "aarch64-apple-darwin",
    "aarch64-apple-ios",
    "aarch64-unknown-linux-gnu",
    "armv7-unknown-linux-gnueabi",
    "armv7-unknown-linux-gnueabihf",
    "arm64-apple-tvos",
    "i686-pc-windows-msvc",
    "i686-unknown-linux-gnu",
    // Note there's build support for mips* targets but they are not tested
    // See https://github.com/astral-sh/python-build-standalone/issues/412
    "mips-unknown-linux-gnu",
    "mipsel-unknown-linux-gnu",
    "mips64el-unknown-linux-gnuabi64",
    "ppc64le-unknown-linux-gnu",
    "riscv64-unknown-linux-gnu",
    "s390x-unknown-linux-gnu",
    "thumbv7k-apple-watchos",
    "x86_64-apple-darwin",
    "x86_64-apple-ios",
    "x86_64-apple-tvos",
    "x86_64-apple-watchos",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "x86_64_v2-unknown-linux-gnu",
    "x86_64_v3-unknown-linux-gnu",
    "x86_64_v4-unknown-linux-gnu",
    "x86_64-unknown-linux-musl",
    "x86_64_v2-unknown-linux-musl",
    "x86_64_v3-unknown-linux-musl",
    "x86_64_v4-unknown-linux-musl",
];

const ELF_ALLOWED_LIBRARIES: &[&str] = &[
    // LSB set.
    "libc.so.6",
    "libdl.so.2",
    "libm.so.6",
    "libpthread.so.0",
    "librt.so.1",
    "libutil.so.1",
];

const PE_ALLOWED_LIBRARIES: &[&str] = &[
    "ADVAPI32.dll",
    "api-ms-win-core-path-l1-1-0.dll",
    "api-ms-win-crt-conio-l1-1-0.dll",
    "api-ms-win-crt-convert-l1-1-0.dll",
    "api-ms-win-crt-heap-l1-1-0.dll",
    "api-ms-win-crt-environment-l1-1-0.dll",
    "api-ms-win-crt-filesystem-l1-1-0.dll",
    "api-ms-win-crt-locale-l1-1-0.dll",
    "api-ms-win-crt-math-l1-1-0.dll",
    "api-ms-win-crt-process-l1-1-0.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll",
    "api-ms-win-crt-stdio-l1-1-0.dll",
    "api-ms-win-crt-string-l1-1-0.dll",
    "api-ms-win-crt-time-l1-1-0.dll",
    "api-ms-win-crt-utility-l1-1-0.dll",
    "bcrypt.dll",
    "Cabinet.dll",
    "COMCTL32.dll",
    "COMDLG32.dll",
    "CRYPT32.dll",
    "GDI32.dll",
    "IMM32.dll",
    "IPHLPAPI.DLL",
    "KERNEL32.dll",
    "msi.dll",
    "NETAPI32.dll",
    "ole32.dll",
    "OLEAUT32.dll",
    "PROPSYS.dll",
    "RPCRT4.dll",
    "SHELL32.dll",
    "SHLWAPI.dll",
    "USER32.dll",
    "USERENV.dll",
    "VERSION.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
    "WINMM.dll",
    "WS2_32.dll",
    // Our libraries.
    "libcrypto-1_1.dll",
    "libcrypto-1_1-x64.dll",
    "libcrypto-3.dll",
    "libcrypto-3-x64.dll",
    "libffi-8.dll",
    "libssl-1_1.dll",
    "libssl-1_1-x64.dll",
    "libssl-3.dll",
    "libssl-3-x64.dll",
    "python3.dll",
    "python39.dll",
    "python310.dll",
    "python311.dll",
    "python312.dll",
    "python313.dll",
    "python313t.dll",
    "python314.dll",
    "python314t.dll",
    "sqlite3.dll",
    "tcl86t.dll",
    "tk86t.dll",
];

// CPython 3.14 uses tcl/tk 8.6.14+ which includes a bundled zlib and dynamically links to msvcrt.
const PE_ALLOWED_LIBRARIES_314: &[&str] = &["msvcrt.dll", "zlib1.dll"];

static GLIBC_MAX_VERSION_BY_TRIPLE: Lazy<HashMap<&'static str, version_compare::Version<'static>>> =
    Lazy::new(|| {
        let mut versions = HashMap::new();

        versions.insert(
            "aarch64-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "armv7-unknown-linux-gnueabi",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "armv7-unknown-linux-gnueabihf",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "i686-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "mips-unknown-linux-gnu",
            version_compare::Version::from("2.19").unwrap(),
        );
        versions.insert(
            "mipsel-unknown-linux-gnu",
            version_compare::Version::from("2.19").unwrap(),
        );
        versions.insert(
            "mips64el-unknown-linux-gnuabi64",
            version_compare::Version::from("2.19").unwrap(),
        );
        versions.insert(
            "ppc64le-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "riscv64-unknown-linux-gnu",
            version_compare::Version::from("2.28").unwrap(),
        );
        versions.insert(
            "s390x-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v2-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v3-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v4-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );

        // musl shouldn't link against glibc.
        versions.insert(
            "x86_64-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v2-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v3-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v4-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );

        versions
    });

static ELF_ALLOWED_LIBRARIES_BY_TRIPLE: Lazy<HashMap<&'static str, Vec<&'static str>>> =
    Lazy::new(|| {
        [
            (
                "armv7-unknown-linux-gnueabi",
                vec!["ld-linux.so.3", "libgcc_s.so.1"],
            ),
            (
                "armv7-unknown-linux-gnueabihf",
                vec!["ld-linux-armhf.so.3", "libgcc_s.so.1"],
            ),
            ("i686-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("mips-unknown-linux-gnu", vec!["ld.so.1", "libatomic.so.1"]),
            (
                "mipsel-unknown-linux-gnu",
                vec!["ld.so.1", "libatomic.so.1"],
            ),
            ("mips64el-unknown-linux-gnuabi64", vec![]),
            ("ppc64le-unknown-linux-gnu", vec!["ld64.so.1", "ld64.so.2"]),
            (
                "riscv64-unknown-linux-gnu",
                vec!["ld-linux-riscv64-lp64d.so.1", "libatomic.so.1"],
            ),
            ("s390x-unknown-linux-gnu", vec!["ld64.so.1"]),
            ("x86_64-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v2-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v3-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v4-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
        ]
        .iter()
        .cloned()
        .collect()
    });

static DARWIN_ALLOWED_DYLIBS: Lazy<Vec<MachOAllowedDylib>> = Lazy::new(|| {
    [
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9d.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.10.dylib".to_string(),
                max_compatibility_version: "3.10.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.10d.dylib".to_string(),
                max_compatibility_version: "3.10.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.11.dylib".to_string(),
                max_compatibility_version: "3.11.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.11d.dylib".to_string(),
                max_compatibility_version: "3.11.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.12.dylib".to_string(),
                max_compatibility_version: "3.12.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.12d.dylib".to_string(),
                max_compatibility_version: "3.12.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.13.dylib".to_string(),
                max_compatibility_version: "3.13.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.13d.dylib".to_string(),
                max_compatibility_version: "3.13.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.13t.dylib".to_string(),
                max_compatibility_version: "3.13.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.13td.dylib".to_string(),
                max_compatibility_version: "3.13.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.14.dylib".to_string(),
                max_compatibility_version: "3.14.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.14d.dylib".to_string(),
                max_compatibility_version: "3.14.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.14t.dylib".to_string(),
                max_compatibility_version: "3.14.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.14td.dylib".to_string(),
                max_compatibility_version: "3.14.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit".to_string(),
                max_compatibility_version: "45.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Cocoa.framework/Versions/A/Cocoa".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name:
                    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation"
                        .to_string(),
                max_compatibility_version: "150.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics".to_string(),
                max_compatibility_version: "64.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreText.framework/Versions/A/CoreText".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation".to_string(),
                max_compatibility_version: "300.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore".to_string(),
                max_compatibility_version: "1.2.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/UniformTypeIdentifiers.framework/Versions/A/UniformTypeIdentifiers".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libedit.3.dylib".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libncurses.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libobjc.A.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libpanel.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libSystem.B.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libz.1.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
        ]
        .to_vec()
});

static IOS_ALLOWED_DYLIBS: Lazy<Vec<MachOAllowedDylib>> = Lazy::new(|| {
    [
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.9.dylib".to_string(),
            max_compatibility_version: "3.9.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.9d.dylib".to_string(),
            max_compatibility_version: "3.9.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.10.dylib".to_string(),
            max_compatibility_version: "3.10.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.10d.dylib".to_string(),
            max_compatibility_version: "3.10.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.11.dylib".to_string(),
            max_compatibility_version: "3.11.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.11d.dylib".to_string(),
            max_compatibility_version: "3.11.0".try_into().unwrap(),
            required: false,
        },
        // For some reason, CoreFoundation is present in debug/noopt builds but not
        // LTO builds.
        MachOAllowedDylib {
            name: "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation".to_string(),
            max_compatibility_version: "150.0.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "/usr/lib/libSystem.B.dylib".to_string(),
            max_compatibility_version: "1.0.0".try_into().unwrap(),
            required: true,
        },
        MachOAllowedDylib {
            name: "/usr/lib/libz.1.dylib".to_string(),
            max_compatibility_version: "1.0.0".try_into().unwrap(),
            required: true,
        },
    ]
    .to_vec()
});

static PLATFORM_TAG_BY_TRIPLE: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    [
        ("aarch64-apple-darwin", "macosx-11.0-arm64"),
        ("aarch64-apple-ios", "iOS-aarch64"),
        ("aarch64-unknown-linux-gnu", "linux-aarch64"),
        ("armv7-unknown-linux-gnueabi", "linux-arm"),
        ("armv7-unknown-linux-gnueabihf", "linux-arm"),
        ("i686-pc-windows-msvc", "win32"),
        ("i686-unknown-linux-gnu", "linux-i686"),
        ("mips-unknown-linux-gnu", "linux-mips"),
        ("mipsel-unknown-linux-gnu", "linux-mipsel"),
        ("mips64el-unknown-linux-gnuabi64", "todo"),
        ("ppc64le-unknown-linux-gnu", "linux-powerpc64le"),
        ("riscv64-unknown-linux-gnu", "linux-riscv64"),
        ("s390x-unknown-linux-gnu", "linux-s390x"),
        ("x86_64-apple-darwin", "macosx-10.15-x86_64"),
        ("x86_64-apple-ios", "iOS-x86_64"),
        ("x86_64-pc-windows-msvc", "win-amd64"),
        ("x86_64-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v2-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v3-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v4-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v2-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v3-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v4-unknown-linux-musl", "linux-x86_64"),
    ]
    .iter()
    .cloned()
    .collect()
});

const ELF_BANNED_SYMBOLS: &[&str] = &[
    // Deprecated as of glibc 2.34 in favor of sched_yield.
    "pthread_yield",
];

/// Symbols defined in dependency packages.
///
/// We use this list to spot test behavior of symbols belonging to dependency packages.
/// The list is obviously not complete.
const DEPENDENCY_PACKAGE_SYMBOLS: &[&str] = &[
    // libX11
    "XClearWindow",
    "XFlush",
    // OpenSSL
    "BIO_ADDR_new",
    "BN_new",
    "DH_new",
    "SSL_extension_supported",
    "SSL_read",
    "CRYPTO_memcmp",
    "ecp_nistz256_neg",
    "OPENSSL_instrument_bus",
    "x25519_fe64_add",
    // libdb
    "__txn_begin",
    // libedit / readline
    "rl_prompt",
    "readline",
    "current_history",
    "history_expand",
    // libffi
    "ffi_call",
    "ffi_type_void",
    // ncurses
    "new_field",
    "set_field_term",
    "set_menu_init",
    "winstr",
    // gdbm
    "gdbm_close",
    "gdbm_import",
    // sqlite3
    "sqlite3_initialize",
    "sqlite3_close",
    // libxcb
    "xcb_create_window",
    "xcb_get_property",
    // libz
    "deflateEnd",
    "gzclose",
    "inflate",
    // tix
    "Tix_DItemCreate",
    "Tix_GrFormat",
    // liblzma
    "lzma_index_init",
    "lzma_stream_encoder",
    // tcl
    "Tcl_Alloc",
    "Tcl_ChannelName",
    "Tcl_CreateInterp",
    // tk
    "TkBindInit",
    "TkCreateFrame",
    "Tk_FreeGC",
];

const PYTHON_EXPORTED_SYMBOLS: &[&str] = &[
    "Py_Initialize",
    "PyList_New",
    // From limited API.
    "Py_CompileString",
];

static WANTED_WINDOWS_STATIC_PATHS: Lazy<BTreeSet<PathBuf>> = Lazy::new(|| {
    [
        PathBuf::from("python/build/lib/libffi.lib"),
        PathBuf::from("python/build/lib/libcrypto_static.lib"),
        PathBuf::from("python/build/lib/liblzma.lib"),
        PathBuf::from("python/build/lib/libssl_static.lib"),
        PathBuf::from("python/build/lib/sqlite3.lib"),
    ]
    .iter()
    .cloned()
    .collect()
});

const GLOBALLY_BANNED_EXTENSIONS: &[&str] = &[
    // Due to linking issues. See comment in cpython.py.
    "nis",
];

const GLOBAL_EXTENSIONS: &[&str] = &[
    "_abc",
    "_ast",
    "_asyncio",
    "_bisect",
    "_blake2",
    "_bz2",
    "_codecs",
    "_codecs_cn",
    "_codecs_hk",
    "_codecs_iso2022",
    "_codecs_jp",
    "_codecs_kr",
    "_codecs_tw",
    "_collections",
    "_contextvars",
    "_csv",
    "_ctypes",
    "_datetime",
    "_decimal",
    "_elementtree",
    "_functools",
    "_hashlib",
    "_heapq",
    "_imp",
    "_io",
    "_json",
    "_locale",
    "_lsprof",
    "_lzma",
    "_md5",
    "_multibytecodec",
    "_multiprocessing",
    "_opcode",
    "_operator",
    "_pickle",
    "_queue",
    "_random",
    "_sha1",
    "_sha3",
    "_signal",
    "_socket",
    "_sqlite3",
    "_sre",
    "_ssl",
    "_stat",
    "_statistics",
    "_string",
    "_struct",
    "_symtable",
    "_thread",
    "_tkinter",
    "_tracemalloc",
    "_warnings",
    "_weakref",
    "_uuid",
    "array",
    "atexit",
    "binascii",
    "builtins",
    "cmath",
    "errno",
    "faulthandler",
    "gc",
    "itertools",
    "marshal",
    "math",
    "mmap",
    "pyexpat",
    "select",
    "sys",
    "time",
    "unicodedata",
    "xxsubtype",
    "zlib",
];

// _zoneinfo added in 3.9.
// parser removed in 3.10.
// _tokenize added in 3.11.
// _typing added in 3.11.
// _testsinglephase added in 3.12.
// _sha256 and _sha512 merged into _sha2 in 3.12.
// _xxinterpchannels added in 3.12.
// audioop removed in 3.13.

// We didn't build ctypes_test until 3.9.
// We didn't build some test extensions until 3.9.

const GLOBAL_EXTENSIONS_PYTHON_3_9: &[&str] = &[
    "audioop",
    "_peg_parser",
    "_sha256",
    "_sha512",
    "_xxsubinterpreters",
    "_zoneinfo",
    "parser",
];

const GLOBAL_EXTENSIONS_PYTHON_3_10: &[&str] = &[
    "audioop",
    "_sha256",
    "_sha512",
    "_xxsubinterpreters",
    "_zoneinfo",
];

const GLOBAL_EXTENSIONS_PYTHON_3_11: &[&str] = &[
    "audioop",
    "_sha256",
    "_sha512",
    "_tokenize",
    "_typing",
    "_xxsubinterpreters",
    "_zoneinfo",
];

const GLOBAL_EXTENSIONS_PYTHON_3_12: &[&str] = &[
    "audioop",
    "_sha2",
    "_tokenize",
    "_typing",
    "_xxinterpchannels",
    "_xxsubinterpreters",
    "_zoneinfo",
];

const GLOBAL_EXTENSIONS_PYTHON_3_13: &[&str] = &[
    "_interpchannels",
    "_interpqueues",
    "_interpreters",
    "_sha2",
    "_suggestions",
    "_sysconfig",
    "_tokenize",
    "_typing",
    "_zoneinfo",
];

const GLOBAL_EXTENSIONS_PYTHON_3_14: &[&str] = &[
    "_interpchannels",
    "_interpqueues",
    "_interpreters",
    "_remote_debugging",
    "_sha2",
    "_suggestions",
    "_sysconfig",
    "_tokenize",
    "_typing",
    "_zoneinfo",
    "_hmac",
    "_types",
];

const GLOBAL_EXTENSIONS_MACOS: &[&str] = &["_scproxy"];

const GLOBAL_EXTENSIONS_POSIX: &[&str] = &[
    "_ctypes_test",
    "_curses",
    "_curses_panel",
    "_dbm",
    "_posixshmem",
    "_posixsubprocess",
    "_testinternalcapi",
    "fcntl",
    "grp",
    "posix",
    "pwd",
    "readline",
    "resource",
    "syslog",
    "termios",
];

const GLOBAL_EXTENSIONS_POSIX_PRE_3_13: &[&str] = &["_crypt"];

const GLOBAL_EXTENSIONS_LINUX_PRE_3_13: &[&str] = &["spwd"];

const GLOBAL_EXTENSIONS_WINDOWS: &[&str] = &[
    "_overlapped",
    "_winapi",
    "msvcrt",
    "nt",
    "winreg",
    "winsound",
];

// TODO(zanieb): Move `_zstd` to non-Windows specific once we add support on Unix.
const GLOBAL_EXTENSIONS_WINDOWS_3_14: &[&str] = &["_wmi", "_zstd"];

const GLOBAL_EXTENSIONS_WINDOWS_PRE_3_13: &[&str] = &["_msi"];

/// Extension modules not present in Windows static builds.
const GLOBAL_EXTENSIONS_WINDOWS_NO_STATIC: &[&str] = &["_testinternalcapi", "_tkinter"];

/// Extension modules that should be built as shared libraries.
const SHARED_LIBRARY_EXTENSIONS: &[&str] = &["_crypt"];

const PYTHON_VERIFICATIONS: &str = include_str!("verify_distribution.py");

fn allowed_dylibs_for_triple(triple: &str) -> Vec<MachOAllowedDylib> {
    match triple {
        "aarch64-apple-darwin" => DARWIN_ALLOWED_DYLIBS.clone(),
        "x86_64-apple-darwin" => DARWIN_ALLOWED_DYLIBS.clone(),
        "aarch64-apple-ios" => IOS_ALLOWED_DYLIBS.clone(),
        "x86_64-apple-ios" => IOS_ALLOWED_DYLIBS.clone(),
        _ => vec![],
    }
}

#[derive(Clone, Default)]
pub struct ValidationContext {
    /// Collected errors.
    pub errors: Vec<String>,

    /// Dynamic libraries required to be loaded.
    pub seen_dylibs: BTreeSet<String>,

    /// Symbols exported from dynamic libpython library.
    pub libpython_exported_symbols: BTreeSet<String>,

    /// Undefined Mach-O symbols that are required / non-weak.
    pub macho_undefined_symbols_strong: RequiredSymbols,

    /// Undefined Mach-O symbols that are weakly referenced.
    pub macho_undefined_symbols_weak: RequiredSymbols,
}

impl ValidationContext {
    /// Merge the contents of `other` into this instance.
    pub fn merge(&mut self, other: Self) {
        self.errors.extend(other.errors);
        self.seen_dylibs.extend(other.seen_dylibs);
        self.libpython_exported_symbols
            .extend(other.libpython_exported_symbols);
        self.macho_undefined_symbols_strong
            .merge(other.macho_undefined_symbols_strong);
        self.macho_undefined_symbols_weak
            .merge(other.macho_undefined_symbols_weak);
    }
}

fn validate_elf<Elf: FileHeader<Endian = Endianness>>(
    context: &mut ValidationContext,
    json: &PythonJsonMain,
    target_triple: &str,
    python_major_minor: &str,
    path: &Path,
    elf: &Elf,
    data: &[u8],
) -> Result<()> {
    let mut system_links = BTreeSet::new();
    for link in &json.build_info.core.links {
        if link.system.unwrap_or_default() {
            system_links.insert(link.name.as_str());
        }
    }
    for extension in json.build_info.extensions.values() {
        for variant in extension {
            for link in &variant.links {
                if link.system.unwrap_or_default() {
                    system_links.insert(link.name.as_str());
                }
            }
        }
    }

    let wanted_cpu_type = match target_triple {
        "aarch64-unknown-linux-gnu" => object::elf::EM_AARCH64,
        "armv7-unknown-linux-gnueabi" => object::elf::EM_ARM,
        "armv7-unknown-linux-gnueabihf" => object::elf::EM_ARM,
        "i686-unknown-linux-gnu" => object::elf::EM_386,
        "mips-unknown-linux-gnu" => object::elf::EM_MIPS,
        "mipsel-unknown-linux-gnu" => object::elf::EM_MIPS,
        "mips64el-unknown-linux-gnuabi64" => 0,
        "ppc64le-unknown-linux-gnu" => object::elf::EM_PPC64,
        "riscv64-unknown-linux-gnu" => object::elf::EM_RISCV,
        "s390x-unknown-linux-gnu" => object::elf::EM_S390,
        "x86_64-unknown-linux-gnu" => object::elf::EM_X86_64,
        "x86_64_v2-unknown-linux-gnu" => object::elf::EM_X86_64,
        "x86_64_v3-unknown-linux-gnu" => object::elf::EM_X86_64,
        "x86_64_v4-unknown-linux-gnu" => object::elf::EM_X86_64,
        "x86_64-unknown-linux-musl" => object::elf::EM_X86_64,
        "x86_64_v2-unknown-linux-musl" => object::elf::EM_X86_64,
        "x86_64_v3-unknown-linux-musl" => object::elf::EM_X86_64,
        "x86_64_v4-unknown-linux-musl" => object::elf::EM_X86_64,
        _ => panic!("unhandled target triple: {}", target_triple),
    };

    let endian = elf.endian()?;

    if elf.e_machine(endian) != wanted_cpu_type {
        context.errors.push(format!(
            "invalid ELF machine type in {}; wanted {}, got {}",
            path.display(),
            wanted_cpu_type,
            elf.e_machine(endian),
        ));
    }

    let mut allowed_libraries = ELF_ALLOWED_LIBRARIES
        .iter()
        .map(|x| x.to_string())
        .collect::<Vec<_>>();
    if let Some(extra) = ELF_ALLOWED_LIBRARIES_BY_TRIPLE.get(target_triple) {
        allowed_libraries.extend(extra.iter().map(|x| x.to_string()));
    }

    if json.libpython_link_mode == "shared" {
        if target_triple.contains("-musl") {
            // On musl, we link to `libpython` and rely on `RUN PATH`
            allowed_libraries.push(format!("libpython{}.so.1.0", python_major_minor));
            allowed_libraries.push(format!("libpython{}d.so.1.0", python_major_minor));
            allowed_libraries.push(format!("libpython{}t.so.1.0", python_major_minor));
            allowed_libraries.push(format!("libpython{}td.so.1.0", python_major_minor));
        } else {
            // On glibc, we can use `$ORIGIN` for relative, reloctable linking
            allowed_libraries.push(format!(
                "$ORIGIN/../lib/libpython{}.so.1.0",
                python_major_minor
            ));
            allowed_libraries.push(format!(
                "$ORIGIN/../lib/libpython{}d.so.1.0",
                python_major_minor
            ));
            allowed_libraries.push(format!(
                "$ORIGIN/../lib/libpython{}t.so.1.0",
                python_major_minor
            ));
            allowed_libraries.push(format!(
                "$ORIGIN/../lib/libpython{}td.so.1.0",
                python_major_minor
            ));
        }
    }

    if !json.build_options.contains("static") && target_triple.contains("-musl") {
        // Allow linking musl `libc`
        allowed_libraries.push("libc.so".to_string());
    }

    // Allow the _crypt extension module - and only it - to link against libcrypt,
    // which is no longer universally present in Linux distros.
    if let Some(filename) = path.file_name() {
        if filename.to_string_lossy().starts_with("_crypt") {
            allowed_libraries.push("libcrypt.so.1".to_string());
        }
    }

    let wanted_glibc_max_version = GLIBC_MAX_VERSION_BY_TRIPLE
        .get(target_triple)
        .expect("max glibc version not defined for target triple");

    let sections = elf.sections(endian, data)?;

    let versions = sections.versions(endian, data)?;

    for (section_index, section) in sections.iter().enumerate() {
        // Dynamic sections defined needed libraries, which we validate.
        if let Some((entries, index)) = section.dynamic(endian, data)? {
            let strings = sections.strings(endian, data, index).unwrap_or_default();

            for entry in entries {
                if entry.tag32(endian) == Some(object::elf::DT_NEEDED) {
                    let lib = entry.string(endian, strings)?;
                    let lib = String::from_utf8(lib.to_vec())?;

                    if !allowed_libraries.contains(&lib.to_string()) {
                        context.errors.push(format!(
                            "{} loads illegal library {}",
                            path.display(),
                            lib
                        ));
                    }

                    // Most linked libraries should have an annotation in the JSON metadata.
                    let requires_annotation = !lib.contains("libpython")
                        && !lib.starts_with("ld-linux")
                        && !lib.starts_with("ld64.so")
                        && !lib.starts_with("ld.so")
                        && !lib.starts_with("libc.so")
                        && !lib.starts_with("libgcc_s.so");

                    if requires_annotation {
                        if lib.starts_with("lib") {
                            if let Some(index) = lib.rfind(".so") {
                                let lib_name = &lib[3..index];

                                // There should be a system links entry for this library in the JSON
                                // metadata.
                                //
                                // Nominally we would look at where this ELF came from and make sure
                                // the annotation is present in its section (e.g. core or extension).
                                // But this is more work.
                                if !system_links.contains(lib_name) {
                                    context.errors.push(format!(
                            "{} library load of {} does not have system link build annotation",
                            path.display(),
                            lib
                        ));
                                }
                            } else {
                                context.errors.push(format!(
                                    "{} library load of {} does not have .so extension",
                                    path.display(),
                                    lib
                                ));
                            }
                        } else {
                            context.errors.push(format!(
                                "{} library load of {} does not begin with lib",
                                path.display(),
                                lib
                            ));
                        }
                    }
                }
            }
        }

        if let Some(symbols) =
            section.symbols(endian, data, &sections, SectionIndex(section_index))?
        {
            let strings = symbols.strings();

            for (symbol_index, symbol) in symbols.iter().enumerate() {
                let name = String::from_utf8_lossy(symbol.name(endian, strings)?);

                // If symbol versions are defined and we're in the .dynsym section, there should
                // be version info for every symbol.
                let version_version = if section.sh_type(endian) == object::elf::SHT_DYNSYM {
                    if let Some(versions) = &versions {
                        let version_index = versions.version_index(endian, symbol_index);

                        if let Some(version) = versions.version(version_index)? {
                            let version = String::from_utf8_lossy(version.name()).to_string();

                            Some(version)
                        } else {
                            None
                        }
                    } else {
                        None
                    }
                } else {
                    None
                };

                if symbol.is_undefined(endian) {
                    if ELF_BANNED_SYMBOLS.contains(&name.as_ref()) {
                        context.errors.push(format!(
                            "{} defines banned ELF symbol {}",
                            path.display(),
                            name,
                        ));
                    }

                    if let Some(version) = version_version {
                        let parts: Vec<&str> = version.splitn(2, '_').collect();

                        if parts.len() == 2 && parts[0] == "GLIBC" {
                            let v = version_compare::Version::from(parts[1])
                                .expect("unable to parse version");

                            if &v > wanted_glibc_max_version {
                                context.errors.push(format!(
                                    "{} references too new glibc symbol {:?} ({} > {})",
                                    path.display(),
                                    name,
                                    v,
                                    wanted_glibc_max_version,
                                ));
                            }
                        }
                    }
                }

                // Ensure specific symbols in dynamic binaries have proper visibility.
                if matches!(elf.e_type(endian), ET_EXEC | ET_DYN) {
                    // Non-local symbols belonging to dependencies should have hidden visibility
                    // to prevent them from being exported.
                    if DEPENDENCY_PACKAGE_SYMBOLS.contains(&name.as_ref())
                        && matches!(symbol.st_bind(), STB_GLOBAL | STB_WEAK)
                        && symbol.st_visibility() != STV_HIDDEN
                    {
                        context.errors.push(format!(
                            "{} contains non-hidden dependency symbol {}",
                            path.display(),
                            name
                        ));
                    }

                    if let Some(filename) = path.file_name() {
                        let filename = filename.to_string_lossy();

                        if filename.starts_with("libpython")
                            && filename.ends_with(".so.1.0")
                            && matches!(symbol.st_bind(), STB_GLOBAL | STB_WEAK)
                            && symbol.st_visibility() == STV_DEFAULT
                        {
                            context.libpython_exported_symbols.insert(name.to_string());
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

#[derive(Debug)]
struct MachOSymbol {
    name: String,
    library_ordinal: u8,
    weak: bool,
}

/// Parses an integer with nibbles xxxx.yy.zz into a [semver::Version].
fn parse_version_nibbles(v: u32) -> semver::Version {
    let major = v >> 16;
    let minor = v << 16 >> 24;
    let patch = v & 0xff;

    semver::Version::new(major as _, minor as _, patch as _)
}

#[allow(clippy::too_many_arguments)]
fn validate_macho<Mach: MachHeader<Endian = Endianness>>(
    context: &mut ValidationContext,
    target_triple: &str,
    advertised_target_version: &str,
    advertised_sdk_version: &str,
    path: &Path,
    header: &Mach,
    bytes: &[u8],
) -> Result<()> {
    let advertised_target_version =
        semver::Version::parse(&format!("{}.0", advertised_target_version))?;
    let advertised_sdk_version = semver::Version::parse(&format!("{}.0", advertised_sdk_version))?;

    let endian = header.endian()?;

    let wanted_cpu_type = match target_triple {
        "aarch64-apple-darwin" => object::macho::CPU_TYPE_ARM64,
        "aarch64-apple-ios" => object::macho::CPU_TYPE_ARM64,
        "x86_64-apple-darwin" => object::macho::CPU_TYPE_X86_64,
        "x86_64-apple-ios" => object::macho::CPU_TYPE_X86_64,
        _ => return Err(anyhow!("unhandled target triple: {}", target_triple)),
    };

    if header.cputype(endian) != wanted_cpu_type {
        context.errors.push(format!(
            "{} has incorrect CPU type; got {}, wanted {}",
            path.display(),
            header.cputype(endian),
            wanted_cpu_type
        ));
    }

    if header.filetype(endian) != MH_OBJECT && header.flags(endian) & MH_TWOLEVEL == 0 {
        context.errors.push(format!(
            "{} does not use two-level symbol lookup",
            path.display()
        ));
    }

    let mut load_commands = header.load_commands(endian, bytes, 0)?;

    let mut dylib_names = vec![];
    let mut undefined_symbols = vec![];
    let mut target_version = None;
    let mut sdk_version = None;

    while let Some(load_command) = load_commands.next()? {
        match load_command.variant()? {
            LoadCommandVariant::BuildVersion(v) => {
                // Sometimes the SDK version is advertised as 0.0.0. In that case just ignore it.
                let version = parse_version_nibbles(v.sdk.get(endian));
                if version > semver::Version::new(0, 0, 0) {
                    sdk_version = Some(version);
                }

                target_version = Some(parse_version_nibbles(v.minos.get(endian)));
            }
            LoadCommandVariant::VersionMin(v) => {
                let version = parse_version_nibbles(v.sdk.get(endian));
                if version > semver::Version::new(0, 0, 0) {
                    sdk_version = Some(version);
                }

                target_version = Some(parse_version_nibbles(v.version.get(endian)));
            }
            LoadCommandVariant::Dylib(command) => {
                let raw_string = load_command.string(endian, command.dylib.name)?;
                let lib = String::from_utf8(raw_string.to_vec())?;

                dylib_names.push(lib.clone());

                let allowed = allowed_dylibs_for_triple(target_triple);

                if let Some(entry) = allowed.iter().find(|l| l.name == lib) {
                    let load_version =
                        MachOPackedVersion::from(command.dylib.compatibility_version.get(endian));

                    if load_version > entry.max_compatibility_version {
                        context.errors.push(format!(
                            "{} loads too new version of {}; got {}, max allowed {}",
                            path.display(),
                            lib,
                            load_version,
                            entry.max_compatibility_version
                        ));
                    }

                    context.seen_dylibs.insert(lib.to_string());
                } else {
                    context.errors.push(format!(
                        "{} loads illegal library {}",
                        path.display(),
                        lib
                    ));
                }
            }
            LoadCommandVariant::Symtab(symtab) => {
                let table = symtab.symbols::<Mach, _>(endian, bytes)?;
                let strings = table.strings();

                for symbol in table.iter() {
                    let name = symbol.name(endian, strings)?;
                    let name = String::from_utf8(name.to_vec())?;

                    if symbol.is_undefined() {
                        undefined_symbols.push(MachOSymbol {
                            name: name.clone(),
                            library_ordinal: symbol.library_ordinal(endian),
                            weak: symbol.n_desc(endian) & (object::macho::N_WEAK_REF) != 0,
                        });
                    }

                    // Ensure specific symbols in dynamic binaries have proper visibility.
                    // Read: we don't want to export symbols from dependencies.
                    if header.filetype(endian) != MH_OBJECT {
                        let n_type = symbol.n_type();

                        let scope = if n_type & object::macho::N_TYPE == object::macho::N_UNDF {
                            SymbolScope::Unknown
                        } else if n_type & object::macho::N_EXT == 0 {
                            SymbolScope::Compilation
                        } else if n_type & object::macho::N_PEXT != 0 {
                            SymbolScope::Linkage
                        } else {
                            SymbolScope::Dynamic
                        };

                        let search_name = if let Some(v) = name.strip_prefix('_') {
                            v
                        } else {
                            name.as_str()
                        };

                        if DEPENDENCY_PACKAGE_SYMBOLS.contains(&search_name)
                            && scope == SymbolScope::Dynamic
                        {
                            context.errors.push(format!(
                                "{} contains dynamic symbol from dependency {}",
                                path.display(),
                                name
                            ));
                        }

                        if let Some(filename) = path.file_name() {
                            let filename = filename.to_string_lossy();

                            if filename.starts_with("libpython")
                                && filename.ends_with(".dylib")
                                && scope == SymbolScope::Dynamic
                            {
                                context
                                    .libpython_exported_symbols
                                    .insert(search_name.to_string());
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    if let Some(actual_target_version) = target_version {
        if actual_target_version != advertised_target_version {
            context.errors.push(format!(
                "{} targets SDK {} but JSON advertises SDK {}",
                path.display(),
                actual_target_version,
                advertised_target_version
            ));
        }
    }

    if let Some(actual_sdk_version) = sdk_version {
        if actual_sdk_version != advertised_sdk_version {
            context.errors.push(format!(
                "{} was built with SDK {} but JSON advertises SDK {}",
                path.display(),
                actual_sdk_version,
                advertised_sdk_version,
            ))
        }
    }

    // Don't perform undefined symbol analysis for object files because the object file
    // in isolation lacks context.
    if header.filetype(endian) != MH_OBJECT {
        for symbol in undefined_symbols {
            // Assume undefined symbols provided by current library will resolve.
            if symbol.library_ordinal == object::macho::SELF_LIBRARY_ORDINAL {
                continue;
            }

            if symbol.library_ordinal < object::macho::MAX_LIBRARY_ORDINAL {
                let lib = dylib_names
                    .get(symbol.library_ordinal as usize - 1)
                    .ok_or_else(|| anyhow!("unable to resolve symbol's library name"))?;

                let symbols = if symbol.weak {
                    &mut context.macho_undefined_symbols_weak
                } else {
                    &mut context.macho_undefined_symbols_strong
                };

                symbols.insert(lib, symbol.name, path.to_path_buf());
            }
        }
    }

    Ok(())
}

fn validate_pe<'data, Pe: ImageNtHeaders>(
    context: &mut ValidationContext,
    python_major_minor: &str,
    path: &Path,
    pe: &PeFile<'data, Pe, &'data [u8]>,
) -> Result<()> {
    // We don't care about the wininst-*.exe distutils executables.
    if path.to_string_lossy().contains("wininst-") {
        return Ok(());
    }

    if let Some(import_table) = pe.import_table()? {
        let mut descriptors = import_table.descriptors()?;

        while let Some(descriptor) = descriptors.next()? {
            let lib = import_table.name(descriptor.name.get(object::LittleEndian))?;
            let lib = String::from_utf8(lib.to_vec())?;

            match python_major_minor {
                "3.9" | "3.10" | "3.11" | "3.12" | "3.13" => {}
                "3.14" => {
                    if PE_ALLOWED_LIBRARIES_314.contains(&lib.as_str()) {
                        continue;
                    }
                }
                _ => {
                    panic!("unhandled Python version: {}", python_major_minor);
                }
            }

            if !PE_ALLOWED_LIBRARIES.contains(&lib.as_str()) {
                context
                    .errors
                    .push(format!("{} loads illegal library {}", path.display(), lib));
            }
        }
    }

    let filename = path
        .file_name()
        .ok_or_else(|| anyhow!("should be able to resolve filename"))?
        .to_string_lossy();

    if filename.starts_with("python") && filename.ends_with(".dll") {
        for symbol in pe.exports()? {
            context
                .libpython_exported_symbols
                .insert(String::from_utf8(symbol.name().to_vec())?);
        }
    }

    Ok(())
}

/// Attempt to parse data as an object file and validate it.
fn validate_possible_object_file(
    json: &PythonJsonMain,
    python_major_minor: &str,
    triple: &str,
    path: &Path,
    data: &[u8],
) -> Result<ValidationContext> {
    let mut context = ValidationContext::default();

    if let Ok(kind) = FileKind::parse(data) {
        match kind {
            FileKind::Elf32 => {
                let header = FileHeader32::parse(data)?;

                validate_elf(
                    &mut context,
                    json,
                    triple,
                    python_major_minor,
                    path,
                    header,
                    data,
                )?;
            }
            FileKind::Elf64 => {
                let header = FileHeader64::parse(data)?;

                validate_elf(
                    &mut context,
                    json,
                    triple,
                    python_major_minor,
                    path,
                    header,
                    data,
                )?;
            }
            FileKind::MachO32 => {
                let header = MachHeader32::parse(data, 0)?;

                validate_macho(
                    &mut context,
                    triple,
                    json.apple_sdk_deployment_target
                        .as_ref()
                        .expect("apple_sdk_deployment_target should be set"),
                    json.apple_sdk_version
                        .as_ref()
                        .expect("apple_sdk_version should be set"),
                    path,
                    header,
                    data,
                )?;
            }
            FileKind::MachO64 => {
                let header = MachHeader64::parse(data, 0)?;

                validate_macho(
                    &mut context,
                    triple,
                    json.apple_sdk_deployment_target
                        .as_ref()
                        .expect("apple_sdk_deployment_target should be set"),
                    json.apple_sdk_version
                        .as_ref()
                        .expect("apple_sdk_version should be set"),
                    path,
                    header,
                    data,
                )?;
            }
            FileKind::MachOFat32 | FileKind::MachOFat64 => {
                if path.to_string_lossy() != "python/build/lib/libclang_rt.osx.a" {
                    context
                        .errors
                        .push(format!("unexpected fat mach-o binary: {}", path.display()));
                }
            }
            FileKind::Pe32 => {
                let file = PeFile32::parse(data)?;
                validate_pe(&mut context, python_major_minor, path, &file)?;
            }
            FileKind::Pe64 => {
                let file = PeFile64::parse(data)?;
                validate_pe(&mut context, python_major_minor, path, &file)?;
            }
            _ => {}
        }
    }

    Ok(context)
}

fn validate_extension_modules(
    python_major_minor: &str,
    target_triple: &str,
    static_crt: bool,
    have_extensions: &BTreeSet<&str>,
) -> Result<Vec<String>> {
    let mut errors = vec![];

    let is_ios = target_triple.contains("-apple-ios");
    let is_macos = target_triple.contains("-apple-darwin");
    let is_linux = target_triple.contains("-unknown-linux-");
    let is_windows = target_triple.contains("-pc-windows-");
    let is_linux_musl = target_triple.contains("-unknown-linux-musl");

    // iOS isn't well supported. So don't do any validation.
    if is_ios {
        return Ok(errors);
    }

    let mut wanted = BTreeSet::from_iter(GLOBAL_EXTENSIONS.iter().copied());

    match python_major_minor {
        "3.9" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_9);
        }
        "3.10" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_10);
        }
        "3.11" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_11);
        }
        "3.12" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_12);
        }
        "3.13" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_13);
        }
        "3.14" => {
            wanted.extend(GLOBAL_EXTENSIONS_PYTHON_3_14);
        }
        _ => {
            panic!("unhandled Python version: {}", python_major_minor);
        }
    }

    if is_macos {
        wanted.extend(GLOBAL_EXTENSIONS_POSIX);

        if matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12") {
            wanted.extend(GLOBAL_EXTENSIONS_POSIX_PRE_3_13);
        }

        wanted.extend(GLOBAL_EXTENSIONS_MACOS);
    }

    if is_windows {
        wanted.extend(GLOBAL_EXTENSIONS_WINDOWS);

        if matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12") {
            wanted.extend(GLOBAL_EXTENSIONS_WINDOWS_PRE_3_13);
        }

        if matches!(python_major_minor, "3.14") {
            wanted.extend(GLOBAL_EXTENSIONS_WINDOWS_3_14);
        }

        if static_crt {
            for x in GLOBAL_EXTENSIONS_WINDOWS_NO_STATIC {
                wanted.remove(*x);
            }
        }
    }

    if is_linux {
        wanted.extend(GLOBAL_EXTENSIONS_POSIX);

        if matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12") {
            wanted.extend(GLOBAL_EXTENSIONS_POSIX_PRE_3_13);
        }

        if matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12") {
            wanted.extend(GLOBAL_EXTENSIONS_LINUX_PRE_3_13);
        }

        if !is_linux_musl && matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12") {
            wanted.insert("ossaudiodev");
        }
    }

    if is_linux || is_macos {
        wanted.extend([
            "_testbuffer",
            "_testimportmultiple",
            "_testmultiphase",
            "_xxtestfuzz",
        ]);
    }

    if (is_linux || is_macos) && matches!(python_major_minor, "3.13") {
        wanted.insert("_testexternalinspection");
    }

    if (is_linux || is_macos) && matches!(python_major_minor, "3.12" | "3.13" | "3.14") {
        wanted.insert("_testsinglephase");
    }

    // _wmi is Windows only on 3.12+.
    if matches!(python_major_minor, "3.12" | "3.13") && is_windows {
        wanted.insert("_wmi");
    }

    for extra in have_extensions.difference(&wanted) {
        errors.push(format!("extra/unknown extension module: {}", extra));
    }

    for missing in wanted.difference(have_extensions) {
        errors.push(format!("missing extension module: {}", missing));
    }

    Ok(errors)
}

fn validate_json(json: &PythonJsonMain, triple: &str, is_debug: bool) -> Result<Vec<String>> {
    let mut errors = vec![];

    if json.version != "8" {
        errors.push(format!(
            "expected version 8 in PYTHON.json; got {}",
            json.version
        ));
    }

    // Distributions built with Apple SDKs should have SDK metadata.
    if triple.contains("-apple-") {
        if json.apple_sdk_canonical_name.is_none() {
            errors.push("JSON missing apple_sdk_canonical_name on Apple triple".to_string());
        }
        if json.apple_sdk_deployment_target.is_none() {
            errors.push("JSON missing apple_sdk_deployment_target on Apple triple".to_string());
        }
        if json.apple_sdk_platform.is_none() {
            errors.push("JSON missing apple_sdk_platform on Apple triple".to_string());
        }
        if json.apple_sdk_version.is_none() {
            errors.push("JSON missing apple_sdk_version on Apple triple".to_string());
        }
    }

    let wanted_platform_tag = *PLATFORM_TAG_BY_TRIPLE
        .get(triple)
        .ok_or_else(|| anyhow!("platform tag not defined for triple {}", triple))?;

    if json.python_platform_tag != wanted_platform_tag {
        errors.push(format!(
            "wanted platform tag {}; got {}",
            wanted_platform_tag, json.python_platform_tag
        ));
    }

    if is_debug
        && !json
            .python_config_vars
            .get("abiflags")
            .unwrap()
            .contains('d')
    {
        errors.push("abiflags does not contain 'd'".to_string());
    }

    for extension in json.build_info.extensions.keys() {
        if GLOBALLY_BANNED_EXTENSIONS.contains(&extension.as_str()) {
            errors.push(format!("banned extension detected: {}", extension));
        }
    }

    let have_extensions = json
        .build_info
        .extensions
        .keys()
        .map(|x| x.as_str())
        .collect::<BTreeSet<_>>();

    errors.extend(validate_extension_modules(
        &json.python_major_minor_version,
        triple,
        json.crt_features.contains(&"static".to_string()),
        &have_extensions,
    )?);

    Ok(errors)
}

fn validate_distribution(
    dist_path: &Path,
    macos_sdks: Option<&IndexedSdks>,
) -> Result<Vec<String>> {
    let mut context = ValidationContext::default();

    let mut seen_paths = BTreeSet::new();
    let mut seen_symlink_targets = BTreeSet::new();

    let dist_filename = dist_path
        .file_name()
        .expect("unable to obtain filename")
        .to_string_lossy();

    let triple = RECOGNIZED_TRIPLES
        .iter()
        .find(|triple| {
            dist_path
                .to_string_lossy()
                .contains(&format!("-{}-", triple))
        })
        .ok_or_else(|| {
            anyhow!(
                "could not identify triple from distribution filename: {}",
                dist_path.display()
            )
        })?;

    let python_major_minor = if dist_filename.starts_with("cpython-3.9.") {
        "3.9"
    } else if dist_filename.starts_with("cpython-3.10.") {
        "3.10"
    } else if dist_filename.starts_with("cpython-3.11.") {
        "3.11"
    } else if dist_filename.starts_with("cpython-3.12.") {
        "3.12"
    } else if dist_filename.starts_with("cpython-3.13.") {
        "3.13"
    } else if dist_filename.starts_with("cpython-3.14.") {
        "3.14"
    } else {
        return Err(anyhow!("could not parse Python version from filename"));
    };

    let is_debug = dist_filename.contains("-debug-");
    let is_static = dist_filename.contains("+static");

    let mut tf = crate::open_distribution_archive(dist_path)?;

    // First entry in archive should be python/PYTHON.json.
    let mut entries = tf.entries()?;

    let mut wanted_python_paths = BTreeSet::new();
    let mut json = None;

    let mut entry = entries.next().unwrap()?;
    if entry.path()?.display().to_string() == "python/PYTHON.json" {
        seen_paths.insert(entry.path()?.to_path_buf());

        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;
        json = Some(parse_python_json(&data).context("parsing PYTHON.json")?);
        context
            .errors
            .extend(validate_json(json.as_ref().unwrap(), triple, is_debug)?);

        wanted_python_paths.extend(
            json.as_ref()
                .unwrap()
                .python_paths
                .values()
                .map(|x| format!("python/{}", x)),
        );
    } else {
        context.errors.push(format!(
            "1st archive entry should be for python/PYTHON.json; got {}",
            entry.path()?.display()
        ));
    }

    let mut bin_python = None;
    let mut bin_python3 = None;

    for entry in entries {
        let mut entry = entry.map_err(|e| anyhow!("failed to iterate over archive: {}", e))?;
        let path = entry.path()?.to_path_buf();

        seen_paths.insert(path.clone());

        if let Some(link_name) = entry.link_name()? {
            let target = path.parent().unwrap().join(link_name).normalize();

            seen_symlink_targets.insert(target);
        }

        // If this path starts with a path referenced in wanted_python_paths,
        // remove the prefix from wanted_python_paths so we don't error on it
        // later.
        let removals = wanted_python_paths
            .iter()
            .filter(|prefix| path.starts_with(prefix))
            .map(|x| x.to_string())
            .collect::<Vec<_>>();
        for p in removals {
            wanted_python_paths.remove(&p);
        }

        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;

        context.merge(validate_possible_object_file(
            json.as_ref().unwrap(),
            python_major_minor,
            triple,
            &path,
            &data,
        )?);

        // Descend into archive files (static libraries are archive files and members
        // are usually object files).
        if let Ok(archive) = goblin::archive::Archive::parse(&data) {
            let mut members = archive.members();
            members.sort();

            for member in members {
                let member_data = archive
                    .extract(member, &data)
                    .with_context(|| format!("extracting {} from {}", member, path.display()))?;

                let member_path = path.with_file_name(format!(
                    "{}:{}",
                    path.file_name().unwrap().to_string_lossy(),
                    member
                ));

                context.merge(validate_possible_object_file(
                    json.as_ref().unwrap(),
                    python_major_minor,
                    triple,
                    &member_path,
                    member_data,
                )?);
            }
        }

        // Verify shebangs don't reference build environment.
        if data.starts_with(b"#!/install") || data.starts_with(b"#!/build") {
            context
                .errors
                .push(format!("{} has #!/install shebang", path.display()));
        }

        if path == PathBuf::from("python/PYTHON.json") {
            context
                .errors
                .push("python/PYTHON.json seen twice".to_string());
        }

        if path == PathBuf::from("python/install/bin/python") {
            if let Some(link) = entry.link_name()? {
                bin_python = Some(link.to_string_lossy().to_string());
            } else {
                context
                    .errors
                    .push("python/install/bin/python is not a symlink".to_string());
            }
        }

        if path == PathBuf::from("python/install/bin/python3") {
            if let Some(link) = entry.link_name()? {
                bin_python3 = Some(link.to_string_lossy().to_string());
            } else {
                context
                    .errors
                    .push("python/install/bin/python3 is not a symlink".to_string());
            }
        }
    }

    match (bin_python, bin_python3) {
        (None, None) => {
            if !triple.contains("-windows-") {
                context
                    .errors
                    .push("install/bin/python and python3 entries missing".to_string());
            }
        }
        (None, Some(_)) => {
            context
                .errors
                .push("install/bin/python symlink missing".to_string());
        }
        (Some(_), None) => {
            context
                .errors
                .push("install/bin/python3 symlink missing".to_string());
        }
        (Some(python), Some(python3)) => {
            if python != python3 {
                context.errors.push(format!(
                    "symlink targets of install/bin/python and python3 vary: {python} !+ {python3}"
                ));
            }
        }
    }

    // We've now read the contents of the archive. Move on to analyzing the results.

    for path in seen_symlink_targets {
        if !seen_paths.contains(&path) {
            context.errors.push(format!(
                "symlink target {} referenced in archive but not found",
                path.display()
            ));
        }
    }

    for path in wanted_python_paths {
        context.errors.push(format!(
            "path prefix {} seen in python_paths does not appear in archive",
            path
        ));
    }

    let wanted_dylibs = BTreeSet::from_iter(
        allowed_dylibs_for_triple(triple)
            .iter()
            .filter(|d| d.required)
            .map(|d| d.name.clone()),
    );

    for lib in wanted_dylibs.difference(&context.seen_dylibs) {
        context
            .errors
            .push(format!("required library dependency {} not seen", lib));
    }

    if triple.contains("-windows-") && is_static {
        for path in WANTED_WINDOWS_STATIC_PATHS.difference(&seen_paths) {
            context
                .errors
                .push(format!("required path {} not seen", path.display()));
        }
    }

    if context.libpython_exported_symbols.is_empty() && !is_static {
        context
            .errors
            .push("libpython does not export any symbols".to_string());
    }

    // Ensure that some well known Python symbols are being exported from libpython.
    for symbol in PYTHON_EXPORTED_SYMBOLS {
        let exported = context.libpython_exported_symbols.contains(*symbol);
        let wanted = !is_static;

        if exported != wanted {
            context.errors.push(format!(
                "libpython {} {}",
                if wanted { "doesn't export" } else { "exports" },
                symbol,
            ));
        }
    }

    // Validate extension module metadata.
    for (name, variants) in json.as_ref().unwrap().build_info.extensions.iter() {
        for ext in variants {
            if let Some(shared) = &ext.shared_lib {
                if !seen_paths.contains(&PathBuf::from("python").join(shared)) {
                    context.errors.push(format!(
                        "extension module {} references missing shared library path {}",
                        name, shared
                    ));
                }
            }

            #[allow(clippy::if_same_then_else)]
            // Static builds never have shared library extension modules.
            let want_shared = if is_static {
                false
            // Extension modules in libpython core are never shared libraries.
            } else if ext.in_core {
                false
            // All remaining extensions are shared on Windows.
            } else if triple.contains("windows") {
                true
            // On POSIX platforms we maintain a list.
            } else {
                SHARED_LIBRARY_EXTENSIONS.contains(&name.as_str())
            };

            if want_shared && ext.shared_lib.is_none() {
                context.errors.push(format!(
                    "extension module {} does not have a shared library",
                    name
                ));
            } else if !want_shared && ext.shared_lib.is_some() {
                context.errors.push(format!(
                    "extension module {} contains a shared library unexpectedly",
                    name
                ));
            }

            // Ensure initialization functions are exported.

            // Note that we export PyInit_* functions from libpython on POSIX whereas these
            // aren't exported from official Python builds. We may want to consider changing
            // this.
            if ext.init_fn == "NULL" {
                continue;
            }

            let exported = context.libpython_exported_symbols.contains(&ext.init_fn);

            #[allow(clippy::needless_bool, clippy::if_same_then_else)]
            // Static distributions never export symbols.
            let wanted = if is_static {
                false
            // For some strange reason _PyWarnings_Init is exported as part of the ABI
            } else if name == "_warnings" {
                // But not on Python 3.13 on Windows
                if triple.contains("-windows-") {
                    matches!(python_major_minor, "3.9" | "3.10" | "3.11" | "3.12")
                } else {
                    true
                }
            // Windows dynamic doesn't export extension module init functions.
            } else if triple.contains("-windows-") {
                false
            // Presence of a shared library extension implies no export.
            } else if ext.shared_lib.is_some() {
                false
            } else {
                true
            };

            if exported != wanted {
                context.errors.push(format!(
                    "libpython {} {} for extension module {}",
                    if wanted { "doesn't export" } else { "exports" },
                    ext.init_fn,
                    name
                ));
            }
        }
    }

    // Validate Mach-O symbols and libraries against what the SDKs say. This is only supported
    // on macOS.
    if triple.contains("-apple-darwin") {
        if let Some(sdks) = macos_sdks {
            if let Some(value) = json.as_ref().unwrap().apple_sdk_deployment_target.as_ref() {
                let target_minimum_sdk = semver::Version::parse(&format!("{}.0", value))?;

                sdks.validate_context(&mut context, target_minimum_sdk, triple)?;
            } else {
                context.errors.push(
                    "cannot perform Apple targeting analysis due to missing SDK advertisement"
                        .into(),
                );
            };
        }
    }

    // Ensure all referenced object paths are in the archive.
    for object_path in json.as_ref().unwrap().all_object_paths() {
        let wanted_path = PathBuf::from("python").join(object_path);

        if !seen_paths.contains(&wanted_path) {
            context.errors.push(format!(
                "PYTHON.json referenced object file not in tar archive: {}",
                wanted_path.display()
            ));
        }
    }

    Ok(context.errors)
}

fn verify_distribution_behavior(dist_path: &Path) -> Result<Vec<String>> {
    let mut errors = vec![];

    let temp_dir = tempfile::TempDir::new()?;

    let mut tf = crate::open_distribution_archive(dist_path)?;

    tf.unpack(temp_dir.path())?;

    let python_json_path = temp_dir.path().join("python").join("PYTHON.json");
    let python_json_data = std::fs::read(python_json_path)?;
    let python_json = parse_python_json(&python_json_data)?;

    let python_exe = temp_dir.path().join("python").join(python_json.python_exe);

    let test_file = temp_dir.path().join("verify.py");
    std::fs::write(&test_file, PYTHON_VERIFICATIONS.as_bytes())?;

    eprintln!("  running interpreter tests (output should follow)");
    let output = duct::cmd(&python_exe, [test_file.display().to_string()])
        .stdout_to_stderr()
        .unchecked()
        .env("TARGET_TRIPLE", &python_json.target_triple)
        .env("BUILD_OPTIONS", &python_json.build_options)
        .run()
        .context(format!(
            "Failed to run `{} {}`",
            python_exe.display(),
            test_file.display()
        ))?;

    if !output.status.success() {
        errors.push("errors running interpreter tests".to_string());
    }

    Ok(errors)
}

pub fn command_validate_distribution(args: &ArgMatches) -> Result<()> {
    let run = args.get_flag("run");

    let macos_sdks = if let Some(path) = args.get_one::<String>("macos_sdks_path") {
        Some(IndexedSdks::new(path)?)
    } else {
        None
    };

    let mut success = true;

    for path in args.get_many::<PathBuf>("path").unwrap() {
        println!("validating {}", path.display());
        let mut errors = validate_distribution(path, macos_sdks.as_ref())?;

        if run {
            errors.extend(verify_distribution_behavior(path)?.into_iter());
        }

        if errors.is_empty() {
            println!("  {} OK", path.display());
        } else {
            for error in errors {
                println!("  error: {}", error);
            }

            success = false;
        }
    }

    if success {
        Ok(())
    } else {
        Err(anyhow!("errors found"))
    }
}
