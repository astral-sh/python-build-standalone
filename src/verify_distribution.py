# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import struct
import sys
import unittest

TERMINFO_DIRS = [
    "/etc/terminfo",
    "/lib/terminfo",
    "/usr/share/terminfo",
]

TCL_PATHS = [
    # POSIX
    ("lib", "tcl", "tcl"),
    # Windows.
    ("tcl",),
]

HERE = os.path.dirname(sys.executable)
INSTALL_ROOT = os.path.dirname(HERE)

# Need to set TCL_LIBRARY so local tcl/tk files get picked up.
for parts in TCL_PATHS:
    candidate = os.path.join(INSTALL_ROOT, *parts)

    if os.path.exists(candidate):
        os.environ["TCL_LIBRARY"] = candidate
        break

# Need to set TERMINFO_DIRS so terminfo database can be located.
if "TERMINFO_DIRS" not in os.environ:
    terminfo_dirs = [p for p in TERMINFO_DIRS if os.path.exists(p)]
    if terminfo_dirs:
        os.environ["TERMINFO_DIRS"] = ":".join(terminfo_dirs)


class TestPythonInterpreter(unittest.TestCase):
    def test_compression(self):
        import bz2
        import lzma
        import zlib

        self.assertTrue(lzma.is_check_supported(lzma.CHECK_CRC64))
        self.assertTrue(lzma.is_check_supported(lzma.CHECK_SHA256))

        bz2.compress(b"test")
        zlib.compress(b"test")

    def test_ctypes(self):
        import ctypes

        # pythonapi will be None on statically linked binaries.
        is_static = "static" in os.environ["BUILD_OPTIONS"]
        if is_static:
            self.assertIsNone(ctypes.pythonapi)
        else:
            self.assertIsNotNone(ctypes.pythonapi)

        # https://bugs.python.org/issue42688
        @ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
        def error_handler(fif, message):
            pass

    @unittest.skipIf(os.name == "nt", "curses not available on Windows")
    def test_curses_import(self):
        import curses

        assert curses is not None

    @unittest.skipIf(os.name == "nt", "curses not available on Windows")
    @unittest.skipIf("TERM" not in os.environ, "TERM not set")
    def test_curses_interactive(self):
        import curses

        curses.initscr()
        curses.endwin()

    def test_hashlib(self):
        import hashlib

        wanted_hashes = {
            "blake2b",
            "blake2s",
            "md5",
            "md5-sha1",
            "ripemd160",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha3_224",
            "sha3_256",
            "sha3_384",
            "sha3_512",
            "sha512",
            "sha512_224",
            "sha512_256",
            "shake_128",
            "shake_256",
            "sm3",
        }

        # Legacy algorithms only present on OpenSSL 1.1.
        if os.name == "nt" and sys.version_info[0:2] < (3, 11):
            wanted_hashes.add("md4")
            wanted_hashes.add("whirlpool")

        for hash in wanted_hashes:
            self.assertIn(hash, hashlib.algorithms_available)

    def test_sqlite(self):
        import sqlite3

        self.assertEqual(sqlite3.sqlite_version_info, (3, 50, 4))

        # Optional SQLite3 features are enabled.
        conn = sqlite3.connect(":memory:")
        # Extension loading enabled.
        self.assertTrue(hasattr(conn, "enable_load_extension"))
        # Backup feature requires modern SQLite, which we always have.
        self.assertTrue(hasattr(conn, "backup"))
        # Ensure that various extensions are present. These will raise if they are not.
        extensions = ["fts3", "fts4", "fts5", "geopoly", "rtree"]
        cursor = conn.cursor()
        for extension in extensions:
            with self.subTest(extension=extension):
                cursor.execute(
                    f"CREATE VIRTUAL TABLE test{extension} USING {extension}(a, b, c);"
                )

        # Test various SQLite flags and features requested / expected by users.
        # The DBSTAT virtual table shows some metadata about disk usage.
        # https://www.sqlite.org/dbstat.html
        self.assertNotEqual(
            cursor.execute("SELECT COUNT(*) FROM dbstat;").fetchone()[0],
            0,
        )

        # The serialize/deserialize API is configurable at compile time.
        if sys.version_info[0:2] >= (3, 11):
            self.assertEqual(conn.serialize()[:15], b"SQLite format 3")

        # The "enhanced query syntax" (-DSQLITE_ENABLE_FTS3_PARENTHESIS) allows parenthesizable
        # AND, OR, and NOT operations. The "standard query syntax" only has OR as a keyword, so we
        # can test for the difference with a query using AND.
        # https://www.sqlite.org/fts3.html#_set_operations_using_the_enhanced_query_syntax
        cursor.execute("INSERT INTO testfts3 VALUES('hello world', '', '');")
        self.assertEqual(
            cursor.execute(
                "SELECT COUNT(*) FROM testfts3 WHERE a MATCH 'hello AND world';"
            ).fetchone()[0],
            1,
        )

        # fts3_tokenizer() takes/returns native pointers. Newer SQLite versions require the use of
        # bound parameters with this function to avoid the risk of a SQL injection esclating into a
        # full RCE. This requirement can be disabled at either compile time or runtime for
        # backwards compatibility. Ensure that the check is enabled (more secure) by default but
        # applications can still use fts3_tokenize with a bound parameter. See discussion at
        # https://github.com/astral-sh/python-build-standalone/pull/562#issuecomment-3254522958
        wild_pointer = struct.pack("P", 0xDEADBEEF)
        with self.assertRaises(sqlite3.OperationalError) as caught:
            cursor.execute(
                f"SELECT fts3_tokenizer('mytokenizer', x'{wild_pointer.hex()}')"
            )
        self.assertEqual(str(caught.exception), "fts3tokenize disabled")
        cursor.execute("SELECT fts3_tokenizer('mytokenizer', ?)", (wild_pointer,))

        conn.close()

    def test_ssl(self):
        import ssl

        self.assertTrue(ssl.HAS_TLSv1)
        self.assertTrue(ssl.HAS_TLSv1_1)
        self.assertTrue(ssl.HAS_TLSv1_2)
        self.assertTrue(ssl.HAS_TLSv1_3)

        # OpenSSL 1.1 on older CPython versions on Windows. 3.5 everywhere
        # else. The format is documented a bit here:
        # https://docs.openssl.org/1.1.1/man3/OPENSSL_VERSION_NUMBER/
        # https://docs.openssl.org/3.5/man3/OpenSSL_version/
        # For 1.x it is the three numerical version components, the
        # suffix letter as a 1-based integer, and 0xF for "release". For
        # 3.x it is the major, minor, 0, patch, and 0.
        if os.name == "nt" and sys.version_info[0:2] < (3, 11):
            wanted_version = (1, 1, 1, 23, 15)
        else:
            wanted_version = (3, 5, 0, 4, 0)

        self.assertEqual(ssl.OPENSSL_VERSION_INFO, wanted_version)

        ssl.create_default_context()

    @unittest.skipIf(
        sys.version_info[:2] < (3, 13),
        "Free-threaded builds are only available in 3.13+",
    )
    def test_gil_disabled(self):
        import sysconfig

        if "freethreaded" in os.environ.get("BUILD_OPTIONS", "").split("+"):
            wanted = 1
        else:
            wanted = 0

        self.assertEqual(sysconfig.get_config_var("Py_GIL_DISABLED"), wanted)

    @unittest.skipIf(
        sys.version_info[:2] < (3, 14),
        "zstd is only available in 3.14+",
    )
    def test_zstd_multithreaded(self):
        from compression import zstd

        max_threads = zstd.CompressionParameter.nb_workers.bounds()[1]
        assert max_threads > 0, (
            "Expected multithreading to be enabled but max threads is zero"
        )

    @unittest.skipIf("TCL_LIBRARY" not in os.environ, "TCL_LIBRARY not set")
    @unittest.skipIf("DISPLAY" not in os.environ, "DISPLAY not set")
    def test_tkinter(self):
        import tkinter as tk

        class Application(tk.Frame):
            def __init__(self, master=None):
                super().__init__(master)
                self.master = master
                self.pack()

                self.hi_there = tk.Button(self)
                self.hi_there["text"] = "Hello World\n(click me)"
                self.hi_there["command"] = self.say_hi
                self.hi_there.pack(side="top")

                self.quit = tk.Button(
                    self, text="QUIT", fg="red", command=self.master.destroy
                )
                self.quit.pack(side="bottom")

            def say_hi(self):
                print("hi there, everyone!")

        root = tk.Tk()
        Application(master=root)

    def test_hash_algorithm(self):
        self.assertTrue(
            sys.hash_info.algorithm.startswith("siphash"),
            msg=f"{sys.hash_info.algorithm=!r} is not siphash",
        )


if __name__ == "__main__":
    unittest.main()
