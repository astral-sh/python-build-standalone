# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.uv]
# no-build = true
# ///
"""Prepare and reassemble PBS install-only archives for the signing rehearsal.

Only native code for the selected platform is replaced. All other files, links,
and archive metadata are retained, and the replacement inventory must match.
The existing release publisher does not consume these experimental outputs.
"""

import argparse
import copy
import hashlib
import io
import json
import os
import struct
import tarfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Member:
    """One TAR member and its data, if it is a regular file."""

    info: tarfile.TarInfo
    data: bytes | None


def sha256(data: bytes) -> str:
    """Return the digest used by GitHub release assets and PBS checksums."""
    return hashlib.sha256(data).hexdigest()


def download(tag: str, version: str, target: str, output: Path) -> None:
    """Download one published stripped archive and verify GitHub's asset digest."""
    name = f"cpython-{version}+{tag}-{target}-install_only_stripped.tar.gz"
    url = (
        "https://api.github.com/repos/astral-sh/python-build-standalone/"
        f"releases/tags/{urllib.parse.quote(tag, safe='')}"
    )
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as source:
        release = json.load(source)
    if release["draft"] or release["tag_name"] != tag:
        raise ValueError("Expected a published release")
    [asset] = [asset for asset in release["assets"] if asset["name"] == name]
    with urllib.request.urlopen(asset["browser_download_url"]) as source:
        data = source.read()
    if asset["digest"] != f"sha256:{sha256(data)}" or asset["size"] != len(data):
        raise ValueError(f"Release asset digest or size differs: {name}")
    output.mkdir(parents=True)
    (output / name).write_bytes(data)
    print(f"Downloaded {name} ({sha256(data)})")


def read_archive(path: Path) -> list[Member]:
    """Read a trusted install-only archive, preserving member order and metadata."""
    members = []
    names = set()
    with tarfile.open(path, "r:gz") as archive:
        for info in archive:
            if info.name in names:
                raise ValueError(f"Duplicate archive member: {info.name}")
            names.add(info.name)
            source = archive.extractfile(info) if info.isfile() else None
            data = source.read() if source is not None else None
            if source is not None:
                source.close()
            members.append(Member(info, data))
    return members


def macho_filetypes(data: bytes) -> set[int]:
    """Read the Mach-O file types from a thin or universal binary's headers."""
    thin = {
        b"\xce\xfa\xed\xfe": "<",
        b"\xcf\xfa\xed\xfe": "<",
        b"\xfe\xed\xfa\xce": ">",
        b"\xfe\xed\xfa\xcf": ">",
    }
    if data[:4] in thin and len(data) >= 16:
        return {struct.unpack_from(thin[data[:4]] + "I", data, 12)[0]}
    fat = {
        b"\xca\xfe\xba\xbe": (">", "I", 20),
        b"\xbe\xba\xfe\xca": ("<", "I", 20),
        b"\xca\xfe\xba\xbf": (">", "Q", 32),
        b"\xbf\xba\xfe\xca": ("<", "Q", 32),
    }
    if data[:4] not in fat or len(data) < 8:
        return set()
    endian, width, record_size = fat[data[:4]]
    count = struct.unpack_from(endian + "I", data, 4)[0]
    if len(data) < 8 + count * record_size:
        return set()
    result = set()
    for index in range(count):
        offset, size = struct.unpack_from(
            endian + width * 2, data, 16 + index * record_size
        )
        result.update(macho_filetypes(data[offset : offset + size]))
    return result


def is_native(data: bytes, system: str) -> bool:
    """Recognize loadable Mach-O images or PE images, independent of filenames."""
    if system == "macos":
        # MH_EXECUTE, MH_DYLIB, and MH_BUNDLE. Object files are not signed.
        return bool(macho_filetypes(data) & {2, 6, 8})
    if data[:2] != b"MZ" or len(data) < 64:
        return False
    offset = struct.unpack_from("<I", data, 60)[0]
    return data[offset : offset + 4] == b"PE\0\0"


def native_members(members: list[Member], system: str) -> dict[str, bytes]:
    """Return every regular native-code member that this platform must sign."""
    binaries = {
        member.info.name: member.data
        for member in members
        if member.data is not None and is_native(member.data, system)
    }
    if not binaries:
        raise ValueError("No native binaries found")
    if system == "windows" and any(
        Path(name).suffix.lower() not in {".exe", ".dll", ".pyd"} for name in binaries
    ):
        raise ValueError("Found a PE image with an unsupported signing extension")
    return binaries


def prepare(archive: Path, system: str, output: Path) -> None:
    """Extract only native code, retaining paths used by the shared signing actions."""
    binaries = native_members(read_archive(archive), system)
    output.mkdir(parents=True)
    for name, data in binaries.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755)
    executables = sorted(
        name for name, data in binaries.items() if 2 in macho_filetypes(data)
    )
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a", encoding="utf-8") as file:
            file.write(f"executables={json.dumps(executables)}\n")
    print(f"Prepared {len(binaries)} {system} binaries from {archive.name}")


def replacements(
    directory: Path, expected: dict[str, bytes], system: str
) -> dict[str, bytes]:
    """Require exactly the prepared native-code paths in the signing output."""
    found = {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
        and not (system == "macos" and path == directory / "certificate.pem")
    }
    if found.keys() != expected.keys():
        raise ValueError(
            f"Signing inventory differs: missing={sorted(expected.keys() - found.keys())}, "
            f"unexpected={sorted(found.keys() - expected.keys())}"
        )
    if any(not is_native(data, system) for data in found.values()):
        raise ValueError("Signing output contains a non-native file")
    return found


def assemble(archive: Path, system: str, signed: Path, output: Path) -> None:
    """Replace all native code and write a new archive with its checksum sidecar."""
    members = read_archive(archive)
    binaries = replacements(signed, native_members(members, system), system)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with tarfile.open(output, "w:gz") as destination:
        for member in members:
            info = copy.copy(member.info)
            data = binaries.get(info.name, member.data)
            if data is not None:
                info.size = len(data)
                if "size" in info.pax_headers:
                    info.pax_headers = {**info.pax_headers, "size": str(len(data))}
            destination.addfile(info, io.BytesIO(data) if data is not None else None)
    output.with_name(f"{output.name}.sha256").write_text(
        f"{sha256(output.read_bytes())}  {output.name}\n", encoding="utf-8"
    )


def check(archive: Path, system: str, signed: Path, assembled: Path) -> None:
    """Check every member's bytes and metadata against its expected replacement."""
    before = read_archive(archive)
    after = read_archive(assembled)
    binaries = replacements(signed, native_members(before, system), system)
    if len(before) != len(after):
        raise ValueError("Archive member count changed")
    for original, actual in zip(before, after, strict=True):
        expected_data = binaries.get(original.info.name, original.data)
        expected_info = original.info.get_info()
        actual_info = actual.info.get_info()
        # TAR header checksums depend on the header encoding, not its metadata.
        del expected_info["chksum"], actual_info["chksum"]
        if expected_data is not None:
            expected_info["size"] = len(expected_data)
        if actual.data != expected_data or actual_info != expected_info:
            raise ValueError(
                f"Archive member changed unexpectedly: {original.info.name}"
            )
        # These PAX fields are already reflected in the metadata checked above.
        fields = {"path", "linkpath", "size", "mtime", "uid", "gid", "uname", "gname"}
        expected_pax = {
            k: v for k, v in original.info.pax_headers.items() if k not in fields
        }
        actual_pax = {
            k: v for k, v in actual.info.pax_headers.items() if k not in fields
        }
        if actual_pax != expected_pax:
            raise ValueError(f"Archive extended metadata changed: {original.info.name}")
    if assembled.with_name(f"{assembled.name}.sha256").read_text().split() != [
        sha256(assembled.read_bytes()),
        assembled.name,
    ]:
        raise ValueError("Assembled archive checksum differs")
    print(f"Checked all {len(after)} members of {assembled.name}")


def main() -> None:
    """Run one phase of the release-signing rehearsal."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("download")
    fetch.add_argument("tag")
    fetch.add_argument("version")
    fetch.add_argument("target")
    fetch.add_argument("output", type=Path)
    for name in ("prepare", "assemble", "check"):
        command = commands.add_parser(name)
        command.add_argument("system", choices=("macos", "windows"))
        command.add_argument("archive", type=Path)
        if name != "prepare":
            command.add_argument("signed", type=Path)
        command.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "download":
        download(args.tag, args.version, args.target, args.output)
    elif args.command == "prepare":
        prepare(args.archive, args.system, args.output)
    elif args.command == "assemble":
        assemble(args.archive, args.system, args.signed, args.output)
    else:
        check(args.archive, args.system, args.signed, args.output)


if __name__ == "__main__":
    main()
