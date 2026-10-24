# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import platform
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    sys.platform in {"linux", "darwin"} and (3, 14) <= sys.version_info[:2] <= (3, 16),
    "relocatable Unix distributions",
)
class TestRelocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(cls.enterClassContext(tempfile.TemporaryDirectory())).resolve()
        cls.prefix = cls.tmp / "moved Python"
        shutil.copytree(
            sys.base_prefix,
            cls.prefix,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "test", "*.a"),
        )
        cls.python = cls.prefix / "bin" / Path(sys.executable).name
        cls.lib = cls.prefix / "lib"
        cls.env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "LD_", "DYLD_", "TCL_", "TK_", "PKG_CONFIG"))
        }
        cls.env["PKG_CONFIG_LIBDIR"] = str(cls.lib / "pkgconfig")
        cls.musl = os.environ["TARGET_TRIPLE"].endswith("-musl")
        cls.cc = ["musl-gcc" if cls.musl else "cc"]
        if sys.platform == "darwin":
            cls.cc += ["-arch", platform.machine()]

    def run_command(self, *args, env=None):
        result = subprocess.run(
            args,
            cwd=self.tmp,
            env=self.env | (env or {}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_installed_paths(self):
        self.assertEqual(sysconfig.get_config_var("RELOCATABLE"), "yes")
        self.assertEqual(sysconfig.get_config_var("Py_ENABLE_RELOCATABLE"), 1)
        result = self.run_command(
            self.python,
            "-I",
            "-c",
            "import sys, sysconfig; print(sys.base_prefix); "
            "print(*sysconfig.get_config_vars('BINDIR', 'LIBDIR', 'LIBPL', 'LDSHARED'), sep='\\n')",
        )
        prefix, bindir, libdir, libpl, ldshared = result.splitlines()
        self.assertEqual(Path(prefix), self.prefix)
        self.assertEqual(Path(bindir), self.python.parent)
        self.assertEqual(Path(libdir), self.lib)
        self.assertTrue(Path(libpl).is_relative_to(self.lib))
        self.assertTrue((Path(libpl) / "Makefile").is_file())
        self.assertNotIn("-rpath", ldshared)
        self.assertEqual(
            self.run_command(self.python.parent / "python3-config", "--prefix").strip(),
            prefix,
        )
        pc_libdir = self.run_command(
            "pkg-config", "--variable=libdir", "python3-embed"
        ).strip()
        self.assertEqual(Path(pc_libdir.replace(r"\ ", " ")).resolve(), self.lib)
        self.assertIn(
            "module errno", self.run_command(self.python.parent / "pydoc3", "errno")
        )
        self.assertIn(
            prefix, self.run_command(self.python.parent / "pip3", "--version")
        )

    def test_library_search_paths(self):
        if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
            self.skipTest("fully static distribution")
        tk = Path(
            self.run_command(
                self.python, "-I", "-c", "import _tkinter; print(_tkinter.__file__)"
            ).strip()
        )
        library = self.lib / sysconfig.get_config_var("INSTSONAME")
        if sys.platform == "darwin":
            self.assertIn(
                f"@rpath/{library.name}", self.run_command("otool", "-D", library)
            )
            self.assertNotIn("libpython", self.run_command("otool", "-L", self.python))
            self.assertIn(
                "path @loader_path/../.. ", self.run_command("otool", "-l", tk)
            )
            dependencies = self.run_command("otool", "-L", tk)
            for name in ("libtcl9.0", "libtcl9tk9.0"):
                self.assertIn(f"@rpath/{name}.dylib", dependencies)
        else:
            maps = self.run_command(
                self.python,
                "-I",
                "-c",
                "import _tkinter; print(open('/proc/self/maps').read())",
            )
            for name in ("libtcl9.0.so", "libtcl9tk9.0.so"):
                self.assertIn(str(self.lib / name), maps)
            for binary, path in (
                (self.python, "$ORIGIN/../lib" if self.musl else None),
                (library, "$ORIGIN"),
                (tk, "$ORIGIN/../.."),
            ):
                with self.subTest(binary=binary):
                    dynamic = self.run_command("readelf", "-d", binary)
                    self.assertNotIn("(RPATH)", dynamic)
                    if path is None:
                        self.assertNotIn("(RUNPATH)", dynamic)
                    else:
                        self.assertIn(f"Library runpath: [{path}]", dynamic)
            self.assertNotIn(
                library.name, self.run_command("readelf", "-d", self.python)
            )
            stub_name = sysconfig.get_config_var("PY3LIBRARY")
            if stub_name:
                stub = self.lib / stub_name
                dynamic = self.run_command("readelf", "-d", stub)
                self.assertIn(f"Shared library: [{library.name}]", dynamic)
                self.assertIn("Library runpath: [$ORIGIN]", dynamic)

    @unittest.skipUnless(sys.platform == "linux", "ELF stable-ABI stub")
    def test_load_stable_abi_stub(self):
        stub = sysconfig.get_config_var("PY3LIBRARY")
        if not sysconfig.get_config_var("Py_ENABLE_SHARED") or not stub:
            self.skipTest("distribution has no stable-ABI stub")
        executable = self.tmp / "load-stub"
        self.run_command(
            *self.cc, Path(__file__).with_name("load_stub.c"), "-ldl", "-o", executable
        )
        self.assertEqual(
            self.run_command(executable, self.lib / stub).strip(), str(self.prefix)
        )

    def test_interpreter_without_shared_library(self):
        if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
            self.skipTest("fully static distribution")
        library = self.lib / sysconfig.get_config_var("INSTSONAME")
        hidden = library.rename(self.tmp / library.name)
        try:
            self.assertEqual(
                self.run_command(
                    self.python, "-I", "-S", "-c", "import sys; print(sys.prefix)"
                ).strip(),
                str(self.prefix),
            )
        finally:
            hidden.rename(library)

    def test_embed(self):
        if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
            self.skipTest("fully static distribution")
        executable = self.tmp / "embed"
        fixture = Path(__file__).with_name("embed.c")
        probe = "import sys, sysconfig; print(sys.base_prefix); print(sysconfig.get_config_var('LIBDIR'))"
        for command in (
            ("pkg-config", "--cflags", "--libs", "python3-embed"),
            (
                self.python.parent / "python3-config",
                "--embed",
                "--includes",
                "--ldflags",
            ),
        ):
            with self.subTest(command=command):
                flags = shlex.split(self.run_command(*command))
                # On Linux the application supplies its own path to libpython.
                if sys.platform == "linux":
                    flags.append(f"-Wl,-rpath,{self.lib}")
                self.run_command(*self.cc, fixture, *flags, "-o", executable)
                self.assertEqual(
                    self.run_command(executable, probe).splitlines(),
                    [str(self.prefix), str(self.lib)],
                )

    @unittest.skipUnless(sys.platform == "linux", "ELF soname lookup")
    def test_extension_linked_to_libpython(self):
        if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
            self.skipTest("fully static distribution")
        soname = sysconfig.get_config_var("INSTSONAME")
        wheel = self.tmp / "wheel"
        wheel.mkdir()
        fixture = Path(__file__).with_name("linked_extension.c")
        self.run_command(
            *self.cc,
            "-shared",
            "-fPIC",
            fixture,
            "-I"
            + str(self.prefix / "include" / Path(sysconfig.get_path("include")).name),
            self.lib / soname,
            "-Wl,--enable-new-dtags,-rpath,$ORIGIN/.libs",
            "-o",
            wheel / "_linked.so",
        )
        foreign = self.tmp / "foreign"
        foreign.mkdir()
        # A valid DSO with the same soname makes accidental selection observable.
        self.run_command(
            *self.cc,
            "-shared",
            "-fPIC",
            "-x",
            "c",
            "/dev/null",
            "-Wl,-soname," + soname,
            "-o",
            foreign / soname,
        )
        probe = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import _linked
assert _linked.none() is None
with open('/proc/self/maps') as maps:
    print(*sorted({line.split(None, 5)[5].strip() for line in maps if sys.argv[2] in line}), sep='\\n')
"""
        cases = [
            (self.python, {}, self.lib),
            (
                self.python,
                {"LD_LIBRARY_PATH": str(foreign)},
                foreign if self.musl else self.lib,
            ),
        ]
        if not self.musl:
            # A copied venv executable has no adjacent libpython.
            venv = self.tmp / "venv"
            self.run_command(
                self.python, "-I", "-m", "venv", "--copies", "--without-pip", venv
            )
            cases.append(
                (venv / "bin" / "python", {"LD_LIBRARY_PATH": str(foreign)}, self.lib)
            )
        for executable, env, selected in cases:
            with self.subTest(executable=executable, env=env):
                paths = self.run_command(
                    executable, "-I", "-c", probe, wheel, soname, env=env
                )
                self.assertEqual(paths.splitlines(), [str(selected / soname)])
        if not self.musl:
            site_packages = self.prefix / Path(
                sysconfig.get_path("purelib")
            ).relative_to(sys.base_prefix)
            pth = site_packages / "linked-wheel.pth"
            pth.write_text(
                f"import sys; sys.path.insert(0, {str(wheel)!r}); import _linked\n"
            )
            self.addCleanup(pth.unlink)
            self.run_command(
                self.python,
                "-I",
                "-c",
                "import sys; assert sys.modules['_linked'].none() is None",
            )
