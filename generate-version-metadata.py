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

    checksum_map: dict[str, str] = {}
    for line in checksums.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        checksum, filename = line.split(maxsplit=1)
        checksum_map[filename.lstrip("*")] = checksum

    versions: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in sorted(dist.glob("cpython-*.tar.*")):
        match = FILENAME_RE.match(path.name)
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
        url = url_prefix + quote(path.name, safe="")
        archive_format = "tar.zst" if path.name.endswith(".tar.zst") else "tar.gz"

        artifact = {
            "platform": match.group("triple"),
            "variant": variant,
            "url": url,
            "archive_format": archive_format,
            "sha256": checksum_map.get(path.name, ""),
        }
        if not artifact["sha256"]:
            artifact.pop("sha256")
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

    payload = {
        "name": "python-build-standalone",
        "versions": payload_versions,
    }

    output = dist / "python-build-standalone.json"
    output.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
