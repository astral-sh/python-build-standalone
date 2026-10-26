# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import hashlib
import importlib.util
import io
import os
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "windows_build", ROOT / "cpython-windows" / "build.py"
)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(mock.patch.object(build, "BUILD", self.root / "build"))
        build.BUILD.mkdir()
        for minor in (11, 12, 13, 14):
            self.pin_source(minor, b"older script" if minor == 11 else b"shared script")
        for name in ["cl.exe", "link.exe", "sh.exe"]:
            path = self.root / name
            path.write_bytes(name.encode())
            path.chmod(0o755)
        self.env = {
            "Path": str(self.root),
            "VCToolsVersion": "14.44.1",
            "WindowsSDKVersion": "10.0.26100.0",
            "GITHUB_ACTIONS": "true",
            "GITHUB_RUN_ID": "123",
            "PYBUILD_LIBFFI_PREPARE_HASHES": " ".join(
                hashlib.sha256(script).hexdigest()
                for script in (b"older script", b"shared script")
            ),
        }
        self.args = argparse.Namespace(
            python="cpython-3.14",
            target_triple="x86_64-pc-windows-msvc",
            vs="2022",
            platform_toolset="v143",
            vc_tools_version="14.4",
            windows_sdk_version="10.0.26100.0",
            options="pgo",
            sh=self.root / "sh.exe",
        )

    def pin_source(self, minor, script):
        entry = build.DOWNLOADS[f"cpython-3.{minor}"]
        source = self.root / f"Python-{entry['version']}.tar.xz"
        with tarfile.open(source, "w:xz") as tf:
            member = tarfile.TarInfo(
                f"Python-{entry['version']}/PCbuild/prepare_libffi.bat"
            )
            member.size = len(script)
            tf.addfile(member, io.BytesIO(script))
        self.enterContext(
            mock.patch.dict(
                entry,
                url=source.as_uri(),
                sha256=build.hash_path(source),
                size=source.stat().st_size,
            )
        )

    def archive(self, dep, **args):
        return build.dependency_archive(
            dep, argparse.Namespace(**(vars(self.args) | args)), self.env
        )

    def test_cpython_variants(self):
        for dep in ("openssl", "libffi"):
            for options in ("debug", "noopt", "freethreaded+pgo", "freethreaded+debug"):
                self.assertEqual(self.archive(dep), self.archive(dep, options=options))
        self.assertEqual(
            self.archive("openssl"), self.archive("openssl", python="cpython-3.12")
        )
        self.assertNotEqual(
            self.archive("openssl"), self.archive("openssl", python="cpython-3.11")
        )
        self.assertNotEqual(
            self.archive("libffi"), self.archive("libffi", python="cpython-3.11")
        )
        self.assertEqual(
            self.archive("libffi"), self.archive("libffi", python="cpython-3.12")
        )

    def test_changed_prepare_script_isolates_unreviewed_sources(self):
        shared = self.archive("libffi")
        changed = b"call another-file-from-cpython.bat"
        for minor in (13, 14):
            self.pin_source(minor, changed)
        unknown = self.archive("libffi")
        prefix = hashlib.sha256(changed).hexdigest()[:7]
        self.assertTrue(unknown.name.startswith(f"libffi-{prefix}-"))
        self.assertNotEqual(shared, unknown)
        self.assertNotEqual(self.archive("libffi", python="cpython-3.13"), unknown)

    def test_script_matching_another_minor_reuses_its_archive(self):
        shared = self.archive("libffi")
        self.pin_source(11, b"shared script")
        self.assertEqual(self.archive("libffi", python="cpython-3.11"), shared)

    def test_no_matrix_hashes_isolates_sources(self):
        self.env.pop("PYBUILD_LIBFFI_PREPARE_HASHES")
        self.assertNotEqual(
            self.archive("libffi"), self.archive("libffi", python="cpython-3.13")
        )

    def test_short_name_collision_does_not_reuse_archive(self):
        with mock.patch.object(build, "hashlib") as hashes:
            hashes.sha256.return_value.hexdigest.side_effect = [
                "abcdef0" + "1" * 57,
                "abcdef0" + "2" * 57,
            ]
            first = self.archive("openssl")
            second = self.archive("openssl", target_triple="i686-pc-windows-msvc")
        first.parent.mkdir()
        first.touch()
        self.assertEqual(first.name, second.name)
        self.assertFalse(second.exists())

    def test_toolchain_and_flags_invalidate(self):
        for dep in ("openssl", "libffi"):
            original = self.archive(dep)
            for field, value in {
                "target_triple": "i686-pc-windows-msvc",
                "vs": "2026",
                "platform_toolset": "v145",
                "vc_tools_version": "14.5",
                "windows_sdk_version": "10.0.22621.0",
            }.items():
                with self.subTest(dep=dep, field=field):
                    self.assertNotEqual(original, self.archive(dep, **{field: value}))
            for field in ("VCToolsVersion", "WindowsSDKVersion", "CFLAGS", "_CL_"):
                with (
                    self.subTest(dep=dep, field=field),
                    mock.patch.dict(self.env, {field: "changed"}),
                ):
                    self.assertNotEqual(original, self.archive(dep))
            cl = self.root / "cl.exe"
            cl.write_bytes(b"compiler updated in place")
            self.assertNotEqual(original, self.archive(dep))
            cl.write_bytes(b"cl.exe")

    def test_sources_and_recipes_invalidate(self):
        for dep, entry in (
            ("openssl", build.OPENSSL_ENTRY),
            ("openssl", "nasm-windows-bin"),
            ("openssl", "jom-windows-bin"),
            ("openssl", "strawberryperl"),
        ):
            original = self.archive(dep)
            with (
                self.subTest(entry=entry),
                mock.patch.dict(build.DOWNLOADS[entry], sha256="new"),
            ):
                self.assertNotEqual(original, self.archive(dep))
        ffi = self.archive("libffi")
        with mock.patch.object(build, "LIBFFI_REVISION", "new"):
            self.assertNotEqual(ffi, self.archive("libffi"))
        with mock.patch.dict(self.env, GITHUB_RUN_ID="another run"):
            self.assertNotEqual(ffi, self.archive("libffi"))

        # Only the uplink build consumes this patch.
        with mock.patch.object(build, "SUPPORT", self.root):
            script = self.root / "build.py"
            script.write_text("recipe")
            patch = self.root / "patch-openssl-uplink.patch"
            patch.write_text("original patch")
            uplink = self.archive("openssl", python="cpython-3.11")
            plain = self.archive("openssl")
            patch.write_text("different patch")
            self.assertNotEqual(uplink, self.archive("openssl", python="cpython-3.11"))
            self.assertEqual(plain, self.archive("openssl"))
            script.write_text("different recipe")
            self.assertNotEqual(plain, self.archive("openssl"))

    def test_produce_restore_and_fallback(self):
        # Use the real CLI, fingerprints, archive format and extraction.
        # Substitute the native build commands so this runs on the check host.
        def make_archive(tmp, directory):
            files = self.root / directory
            files.mkdir(exist_ok=True)
            (files / "library.dll").write_bytes(b"fixture")
            with tmp.open("wb") as fh:
                build.create_tar_from_directory(fh, files, directory)

        def consume(python, triple, arch, *, openssl_archive, libffi_archive, **kwargs):
            for dep, archive in (
                ("openssl", openssl_archive),
                ("libffi", libffi_archive),
            ):
                with tarfile.open(archive) as tf:
                    self.assertEqual(
                        tf.extractfile(f"{dep}/library.dll").read(), b"fixture"
                    )
            return self.root / "cpython.tar"

        self.enterContext(mock.patch.object(build, "LOG_FH", [None]))
        self.enterContext(mock.patch.dict(os.environ, PYBUILD_RELEASE_TAG="test"))
        self.enterContext(mock.patch.object(build, "DIST", self.root / "dist"))
        self.enterContext(
            mock.patch.object(
                build, "get_visual_studio_environment", return_value=self.env
            )
        )
        perl = self.enterContext(
            mock.patch.object(build, "fetch_strawberry_perl", return_value=self.root)
        )
        ssl = self.enterContext(
            mock.patch.object(
                build,
                "build_openssl",
                side_effect=lambda entry, perl, arch, tmp, with_uplink: make_archive(
                    tmp, "openssl"
                ),
            )
        )
        ffi = self.enterContext(
            mock.patch.object(
                build,
                "build_libffi",
                side_effect=lambda python, arch, sh, vs, vc, tmp: make_archive(
                    tmp, "libffi"
                ),
            )
        )
        cpython = self.enterContext(
            mock.patch.object(build, "build_cpython", side_effect=consume)
        )
        self.enterContext(mock.patch.object(build, "compress_python_archive"))

        def run(job, *args):
            with (
                mock.patch.object(build, "BUILD", self.root / job),
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "build.py",
                        "--target-triple",
                        self.args.target_triple,
                        "--python",
                        self.args.python,
                        "--sh",
                        str(self.args.sh),
                        *args,
                    ],
                ),
            ):
                build.main()

        keys = self.root / "outputs"
        run("consumer", "--write-dependency-keys", str(keys))
        archives = dict(line.split("=") for line in keys.read_text().splitlines())
        self.assertRegex(
            archives["openssl"], r"^[0-9a-f]{64}/openssl-[0-9a-f]{7}\.tar$"
        )
        self.assertRegex(
            archives["libffi"], r"^[0-9a-f]{64}/libffi-[0-9a-f]{7}-[0-9a-f]{7}\.tar$"
        )
        for dep in ("openssl", "libffi"):
            run(dep, "--dependency", dep)
            restored = self.root / "consumer" / archives[dep]
            restored.parent.mkdir()
            shutil.copy(self.root / dep / archives[dep], restored)
        cpython.assert_not_called()
        run("consumer", "--python", "cpython-3.13", "--options", "freethreaded+debug")
        self.assertEqual((ssl.call_count, ffi.call_count, perl.call_count), (1, 1, 1))
        self.assertEqual(
            cpython.call_args.kwargs["build_options"], "freethreaded+debug"
        )

        self.pin_source(14, b"updated script")
        new_keys = self.root / "new-outputs"
        run("consumer", "--write-dependency-keys", str(new_keys))
        changed = dict(line.split("=") for line in new_keys.read_text().splitlines())
        self.assertEqual(archives["openssl"], changed["openssl"])
        self.assertNotEqual(archives["libffi"], changed["libffi"])
        self.assertFalse((self.root / "consumer" / changed["libffi"]).exists())
        run("consumer")
        self.assertEqual((ssl.call_count, ffi.call_count), (1, 2))
        self.assertEqual(cpython.call_count, 2)
        run("consumer")
        self.assertEqual((ssl.call_count, ffi.call_count), (1, 2))

    def test_failure_does_not_publish_partial_archive(self):
        def fail(python, arch, sh, vs, vc, tmp):
            tmp.write_bytes(b"partial")
            raise RuntimeError("failed")

        archive = self.root / "libffi.tar"
        with (
            mock.patch.object(build, "BUILD", self.root),
            mock.patch.object(build, "build_libffi", side_effect=fail),
        ):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                build.ensure_dependency("libffi", archive, self.args)
        self.assertFalse(archive.exists())
