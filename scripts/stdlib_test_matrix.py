# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generate a stdlib test matrix from existing GitHub Actions build artifacts.

Requires an authenticated gh CLI (or GH_TOKEN). For local use:

    uv run scripts/stdlib_test_matrix.py --repository OWNER/REPO --sha SHA \
        --matrix-dir /path/to/matrices

The matrix directory must contain linux.json, macos.json, and windows.json from
ci-matrix.py at the requested SHA, with any desired filters already applied.
Generate the inputs without sharding. Linux entries are sharded after artifact
filtering. The final matrix is printed as JSON; --github-output additionally
writes workflow step outputs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PLATFORMS = ("linux", "macos", "windows")
MATRIX_SIZE_LIMIT = 256
# Keep this in sync with the Linux jobs and outputs in stdlib.yml.
LINUX_SHARD_COUNT = 2


def load_candidates(matrix_dir: Path) -> dict[str, Any]:
    """Read the unsharded ci-matrix.py outputs for each platform."""
    matrices = {}
    for platform in PLATFORMS:
        with (matrix_dir / f"{platform}.json").open(encoding="utf-8") as source:
            matrices[platform] = json.load(source)["python-build"]
    return matrices


def github_api(endpoint: str, *, paginate: bool = False, **params: str) -> Any:
    command = ["gh", "api", "--method", "GET", endpoint, "-f", "per_page=100"]
    for name, value in params.items():
        command.extend(["-f", f"{name}={value}"])
    if paginate:
        command.extend(["--paginate", "--slurp"])
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
    return json.loads(result.stdout)


def find_build_run(repository: str, sha: str, platform: str) -> str | None:
    """Select the latest successful platform build for the requested commit."""
    response = github_api(
        f"repos/{repository}/actions/workflows/{platform}.yml/runs",
        head_sha=sha,
        status="success",
    )
    runs = response["workflow_runs"]
    return str(runs[0]["id"]) if runs else None


def list_artifacts(repository: str, run_id: str) -> set[str]:
    """Collect unexpired artifact names across all pages of the selected run."""
    pages = github_api(
        f"repos/{repository}/actions/runs/{run_id}/artifacts", paginate=True
    )
    return {
        artifact["name"]
        for page in pages
        for artifact in page["artifacts"]
        if not artifact["expired"]
    }


def intersect_matrix(matrix: dict[str, Any], artifacts: set[str]) -> dict[str, Any]:
    entries = []
    for entry in matrix["include"]:
        if entry["run"] != "true":
            continue
        # Windows artifact names use vcvars rather than the target triple.
        target = entry.get("vcvars", entry["target_triple"])
        name = f"cpython-{entry['python']}-{target}-{entry['build_options']}"
        if name in artifacts:
            entries.append(entry)
    return {**matrix, "include": entries}


def shard_linux_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    """Pack filtered entries into the workflow's Linux jobs, including empty shards."""
    entries = matrix["include"]
    if len(entries) > MATRIX_SIZE_LIMIT * LINUX_SHARD_COUNT:
        raise ValueError(
            f"Filtered Linux matrix has {len(entries)} entries, exceeding "
            f"{LINUX_SHARD_COUNT} shards of {MATRIX_SIZE_LIMIT}; add Linux jobs "
            "to stdlib.yml and increase LINUX_SHARD_COUNT."
        )
    return {
        f"linux-{index}": {
            **matrix,
            "include": entries[
                index * MATRIX_SIZE_LIMIT : (index + 1) * MATRIX_SIZE_LIMIT
            ],
        }
        for index in range(LINUX_SHARD_COUNT)
    }


def generate_test_matrix(
    repository: str, sha: str, matrix_dir: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    candidates = load_candidates(matrix_dir)
    matrices = {}
    run_ids = {}
    for platform in PLATFORMS:
        artifacts: set[str] = set()
        if any(entry["run"] == "true" for entry in candidates[platform]["include"]):
            run_id = find_build_run(repository, sha, platform)
            if run_id is None:
                print(
                    f"No successful {platform} build workflow found for {sha}; "
                    f"skipping {platform}.",
                    file=sys.stderr,
                )
            else:
                artifacts = list_artifacts(repository, run_id)
                run_ids[platform] = run_id
        filtered = intersect_matrix(candidates[platform], artifacts)
        if platform == "linux":
            matrices.update(shard_linux_matrix(filtered))
        else:
            matrices[platform] = filtered

    if not any(matrix["include"] for matrix in matrices.values()):
        raise ValueError(
            "No unexpired distribution artifacts match the requested test matrix "
            "in successful build workflows."
        )
    return matrices, run_ids


def write_github_outputs(
    path: Path, matrices: dict[str, Any], run_ids: dict[str, str]
) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, matrix in matrices.items():
            matrix_key = (
                key.replace("linux-", "linux-matrix-")
                if key.startswith("linux-")
                else f"{key}-matrix"
            )
            print(
                f"{matrix_key}={json.dumps(matrix, separators=(',', ':'))}", file=output
            )
            print(f"any-{key}={str(bool(matrix['include'])).lower()}", file=output)
        for platform, run_id in run_ids.items():
            print(f"{platform}-run-id={run_id}", file=output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub OWNER/REPO")
    parser.add_argument(
        "--sha", required=True, help="Commit with completed build workflows"
    )
    parser.add_argument(
        "--matrix-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing linux.json, macos.json, and windows.json",
    )
    parser.add_argument(
        "--github-output", type=Path, help="Optional GitHub step output file"
    )
    args = parser.parse_args(argv)
    try:
        matrices, run_ids = generate_test_matrix(
            args.repository, args.sha, args.matrix_dir.resolve()
        )
        if args.github_output is not None:
            write_github_outputs(args.github_output, matrices, run_ids)
        print(json.dumps(matrices, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error generating stdlib test matrix: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
