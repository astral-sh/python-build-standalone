"""Exercise an assembled Python's native modules, callbacks, venv, and pip."""

import ctypes
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import tkinter
import venv
from pathlib import Path


def main() -> None:
    """Check native loading, executable memory, and a third-party extension wheel."""
    print(sys.version)
    print(ssl.OPENSSL_VERSION)
    assert sqlite3.connect(":memory:").execute("select 42").fetchone() == (42,)
    print(tkinter.Tcl().eval("info patchlevel"))
    callback = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 42)
    assert callback() == 42
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(directory)
        python = directory / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        subprocess.run(
            [
                python,
                "-m",
                "pip",
                "--isolated",
                "--disable-pip-version-check",
                "install",
                "--index-url",
                "https://pypi.org/simple",
                "--no-cache-dir",
                "--only-binary=:all:",
                "cffi",
            ],
            check=True,
        )
        subprocess.run(
            [
                python,
                "-I",
                "-c",
                "import _cffi_backend; from cffi import FFI; f = FFI().callback('int(void)', lambda: 42); assert f() == 42",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
