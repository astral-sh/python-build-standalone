# /// script
# requires-python = ">=3.11"
# ///
"""Generate versions payload for python-build-standalone releases."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

FILENAME_RE = re.compile(
    r"""(?x)
    ^
        cpython-
        (?P<py>\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)(?:\+\d+)?\+
        (?P<tag>\d+)-
        (?P<triple>[a-z\d_]+-[a-z\d]+(?:-[a-z\d]+)?-[a-z\d_]+)-
        (?:(?P<build>.+)-)?
        (?P<flavor>[a-z_]+)?
        \.tar\.(?:gz|zst)
    $
    """
)


def main() -> None:
    tag = os.environ["GITHUB_EVENT_INPUTS_TAG"]
    repo = os.environ["GITHUB_REPOSITORY"]
    dist = Path("dist")
    checksums = dist / "SHA256SUMS"

    if not checksums.exists():
        raise SystemExit("SHA256SUMS not found in dist/")

    # Parse filenames and checksums directly from SHA256SUMS to avoid downloading
    # all release artifacts (tens of GB).
    entries: list[tuple[str, str]] = []
    for line in checksums.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        checksum, filename = line.split(maxsplit=1)
        filename = filename.lstrip("*")
        entries.append((filename, checksum))

    versions: dict[str, list[dict[str, str]]] = defaultdict(list)
    for filename, checksum in sorted(entries):
        match = FILENAME_RE.match(filename)
        if match is None:
            continue
        python_version = match.group("py")
        build_version = match.group("tag")
        version = f"{python_version}+{build_version}"
        build = match.group("build")
        flavor = match.group("flavor")
        variant_parts: list[str] = []
        if build:
            variant_parts.extend(build.split("+"))
        if flavor:
            variant_parts.append(flavor)
        variant = "+".join(variant_parts) if variant_parts else ""

        url_prefix = f"https://github.com/{repo}/releases/download/{tag}/"
        url = url_prefix + quote(filename, safe="")
        archive_format = "tar.zst" if filename.endswith(".tar.zst") else "tar.gz"

        artifact = {
            "platform": match.group("triple"),
            "variant": variant,
            "url": url,
            "archive_format": archive_format,
            "sha256": checksum,
        }
        versions[version].append(artifact)

    payload_versions: list[dict[str, object]] = []
    now = datetime.now(timezone.utc).isoformat()
    for version, artifacts in sorted(versions.items(), reverse=True):
        artifacts.sort(
            key=lambda artifact: (artifact["platform"], artifact.get("variant", ""))
        )
        payload_versions.append(
            {
                "version": version,
                "date": now,
                "artifacts": artifacts,
            }
        )

    for version in payload_versions:
        print(json.dumps(version, separators=(",", ":")))


if __name__ == "__main__":
    main()
