#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Adapted from toolchain-tools/toolchain-bootstrap/scripts/clang-macos.py
# from the toolchain-tools project by indygreg
# https://github.com/indygreg/toolchain-tools

import gzip
import hashlib
import http.client
import multiprocessing
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from compression import zstd

ROOT = Path(__file__).resolve().parent

# 2021-01-01T00:00:00
DEFAULT_MTIME = 1609488000

COMPRESSION_LEVEL = 18

DOWNLOADS = {
    "cmake": {
        "url": "https://github.com/Kitware/CMake/releases/download/v4.4.3/cmake-4.4.3-macos-universal.tar.gz",
        "size": 89445170,
        "sha256": "0c5d65251c14cc884bfa16bdbed3c263ce5bffe2e21c0d0d00962cb0610464fa",
        "version": "4.4.3",
    },
    "ninja": {
        "url": "https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-mac.zip",
        "size": 314051,
        "sha256": "c99048673aa765960a99cf10c6ddb9f1fad506099ff0a0e137ad8960a88f321b",
        "version": "1.13.2",
    },
    "llvm": {
        "url": "https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.1/llvm-project-23.1.1.src.tar.xz",
        "size": 179168672,
        "sha256": "ebe9be46fe8756d58c5b198ffad0fa2a766257add81a4dc52179bfacc7888ee6",
        "version": "23.1.1",
    },
    "sccache": {
        "url": "https://github.com/mozilla/sccache/releases/download/v0.18.0/sccache-v0.18.0-aarch64-apple-darwin.tar.gz",
        "size": 7997637,
        "sha256": "308184519b646f5125289e8515b36f6ca65a13a041923994aebe702348674e8e",
        "version": "0.18.0",
    },
}

# Much of this functionality exists in pythonbuild/utils.py
# An independent copy is used here to keep this script self-contained.


def hash_path(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


class IntegrityError(Exception):
    """Represents an integrity error when downloading a URL."""

    def __init__(self, *args, length: int):
        self.length = length
        super().__init__(*args)


def secure_download_stream(url: str, size: int, sha256: str):
    """Securely download a URL to a stream of chunks.

    If the integrity of the download fails, an IntegrityError is
    raised.
    """
    h = hashlib.sha256()
    length = 0

    with urllib.request.urlopen(url) as fh:
        if not url.endswith(".gz") and fh.info().get("Content-Encoding") == "gzip":
            fh = gzip.GzipFile(fileobj=fh)

        while chunk := fh.read(65536):
            h.update(chunk)
            length += len(chunk)

            yield chunk

    digest = h.hexdigest()

    if length != size or digest != sha256:
        raise IntegrityError(
            f"integrity mismatch on {url}: wanted size={size}, sha256={sha256}; "
            f"got size={length}, sha256={digest}",
            length=length,
        )


def download_to_path(url: str, path: Path, size: int, sha256: str) -> None:
    """Download a file, validating its size and SHA-256 digest."""

    # We download to a temporary file and rename at the end so there's
    # no chance of the final file being partially written or containing
    # bad data.
    print(f"downloading {url} to {path}")

    if path.exists():
        if path.stat().st_size != size:
            print("existing file size is wrong; removing")
        elif hash_path(path) != sha256:
            print("existing file hash is wrong; removing")
        else:
            print(f"{path} exists and passes integrity checks")
            return

        path.unlink()

    for attempt in range(8):
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f"{path.name}.tmp",
            delete_on_close=False,
        ) as fh:
            try:
                fh.writelines(secure_download_stream(url, size, sha256))
            except IntegrityError as e:
                # If we didn't get most of the expected file, retry.
                if e.length > size * 0.75:
                    raise
                print(f"Integrity error on {url}; retrying: {e}")
            except (http.client.HTTPException, urllib.error.URLError) as e:
                print(f"Network error on {url}; retrying: {e}")
            else:
                fh.close()
                Path(fh.name).rename(path)
                print(f"successfully downloaded {url}")
                return

        time.sleep(2**attempt)

    raise Exception(f"download failed after multiple retries: {url}")


def create_normalized_tar_from_directory(
    fh, base_path: Path, path_prefix: str | None = None
) -> None:
    """Write a tar with deterministic ordering, timestamps, ownership, and modes."""

    def normalize_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.pax_headers = {}
        info.mtime = DEFAULT_MTIME
        info.uid = info.gid = 0
        info.uname = info.gname = "root"

        # Give user/group read/write on all entries.
        info.mode |= stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP

        # If user executable, give to group as well.
        if info.mode & stat.S_IXUSR:
            info.mode |= stat.S_IXGRP

        return info

    prefix = Path(path_prefix or "")

    with tarfile.open(fileobj=fh, mode="w") as archive:
        for root, directories, files in os.walk(base_path):
            directories.sort()

            for name in directories + sorted(files):
                source_path = Path(root) / name
                archive_path = prefix / source_path.relative_to(base_path)

                archive.add(
                    source_path,
                    arcname=archive_path.as_posix(),
                    recursive=False,
                    filter=normalize_tarinfo,
                )


def build_llvm(build_path: Path) -> Path:
    build_path = build_path.resolve()
    build_path.mkdir(parents=True, exist_ok=True)
    script = ROOT / "scripts" / "clang-macos.sh"
    downloaded_paths = []

    for entry in DOWNLOADS.values():
        filename = entry["url"].rsplit("/", 1)[-1]
        dest = build_path / filename

        download_to_path(entry["url"], dest, entry["size"], entry["sha256"])
        downloaded_paths.append(dest)

    with tempfile.TemporaryDirectory(prefix="pbs-toolchain-") as td:
        temp_dir = Path(td)

        for path in downloaded_paths:
            shutil.copy(path, temp_dir / path.name)

        shutil.copy(script, temp_dir / script.name)

        env = os.environ.copy()
        env.pop("PYTHONSAFEPATH", None)
        env.pop("VIRTUAL_ENV", None)
        env["SCCACHE_DIR"] = env.get("SCCACHE_DIR") or str(build_path / "sccache")
        env["SCCACHE_BASEDIRS"] = str(temp_dir.resolve())
        for name, entry in DOWNLOADS.items():
            env[f"{name.upper()}_VERSION"] = entry["version"]

        cpu_count = multiprocessing.cpu_count()
        env["NUM_CPUS"] = str(cpu_count)
        env["NUM_JOBS_AGGRESSIVE"] = str(max(cpu_count + 2, cpu_count * 2))
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"

        env["HOST_TRIPLE"] = "arm64-apple-darwin23.2.0"

        subprocess.run(
            [str(temp_dir / script.name)],
            cwd=temp_dir,
            env=env,
            check=True,
            stderr=subprocess.STDOUT,
        )

        dest_path = build_path / "llvm-aarch64-apple-darwin.tar.zst"
        print(f"writing {dest_path}")

        with zstd.open(dest_path, "wb", level=COMPRESSION_LEVEL) as fh:
            create_normalized_tar_from_directory(
                fh, temp_dir / "out" / "toolchain", "llvm"
            )

        return dest_path


if __name__ == "__main__":
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        sys.exit("Run this script natively on an ARM64 macOS host.")
    sys.stdout.reconfigure(line_buffering=True)
    build_llvm(ROOT / "build")
