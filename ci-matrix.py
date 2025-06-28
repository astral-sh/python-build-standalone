# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "packaging",
#     "pyyaml",
# ]
# ///

import argparse
import json
import sys
from typing import Any, Optional

import yaml
from packaging.version import Version

CI_TARGETS_YAML = "ci-targets.yaml"
CI_RUNNERS_YAML = "ci-runners.yaml"
CI_EXTRA_SKIP_LABELS = ["documentation"]
CI_MATRIX_SIZE_LIMIT = 256  # The maximum size of a matrix in GitHub Actions


# Docker images for building toolchains and dependencies
DOCKER_BUILD_IMAGES = [
    {"name": "build", "arch": "x86_64"},
    {"name": "build.cross", "arch": "x86_64"},
    {"name": "build.cross-riscv64", "arch": "x86_64"},
    {"name": "gcc", "arch": "x86_64"},
]


def crate_artifact_name(platform: str, arch: str) -> str:
    return f"crate-{platform}-{arch}"


def meets_conditional_version(version: str, min_version: str) -> bool:
    return Version(version) >= Version(min_version)


def parse_labels(labels: Optional[str]) -> dict[str, set[str]]:
    """Parse labels into a dict of category filters."""
    if not labels:
        return {}

    result: dict[str, set[str]] = {
        "platform": set(),
        "python": set(),
        "build": set(),
        "arch": set(),
        "libc": set(),
        "directives": set(),
    }

    for label in labels.split(","):
        label = label.strip()

        # Handle special labels
        if label in CI_EXTRA_SKIP_LABELS:
            result["directives"].add("skip")
            continue

        if not label or ":" not in label:
            continue

        category, value = label.split(":", 1)

        if category == "ci":
            category = "directives"

        if category in result:
            result[category].add(value)

    return result


def should_include_entry(entry: dict[str, str], filters: dict[str, set[str]]) -> bool:
    """Check if an entry satisfies the label filters."""
    if filters.get("directives") and "skip" in filters["directives"]:
        return False

    if filters.get("platform") and entry["platform"] not in filters["platform"]:
        return False

    if filters.get("python") and entry["python"] not in filters["python"]:
        return False

    if filters.get("arch") and entry["arch"] not in filters["arch"]:
        return False

    if (
        filters.get("libc")
        and entry.get("libc")
        and entry["libc"] not in filters["libc"]
    ):
        return False

    if filters.get("build"):
        build_options = set(entry.get("build_options", "").split("+"))
        if not all(f in build_options for f in filters["build"]):
            return False

    return True


def generate_docker_matrix_entries(
    runners: dict[str, Any],
    platform_filter: Optional[str] = None,
) -> list[dict[str, str]]:
    """Generate matrix entries for docker image builds."""
    if platform_filter and platform_filter != "linux":
        return []

    matrix_entries = []
    for image in DOCKER_BUILD_IMAGES:
        # Find appropriate runner for Linux platform with the specified architecture
        runner = find_runner(runners, "linux", image["arch"], False)

        entry = {
            "name": image["name"],
            "arch": image["arch"],
            "runner": runner,
        }
        matrix_entries.append(entry)

    return matrix_entries


def generate_crate_build_matrix_entries(
    python_entries: list[dict[str, str]],
    runners: dict[str, Any],
    config: dict[str, Any],
    force_crate_build: bool = False,
    platform_filter: Optional[str] = None,
) -> list[dict[str, str]]:
    """Generate matrix entries for crate builds based on python build matrix."""
    needed_builds = set()
    for entry in python_entries:
        # The crate build will need to match the runner's architecture
        runner = runners[entry["runner"]]
        needed_builds.add((entry["platform"], runner["arch"]))

    # If forcing crate build, also include all possible native builds
    if force_crate_build:
        for platform, platform_config in config.items():
            # Filter by platform if specified
            if platform_filter and platform != platform_filter:
                continue

            for target_config in platform_config.values():
                # Only include if native (run: true means native)
                if not target_config.get("run"):
                    continue

                arch = target_config["arch"]
                needed_builds.add((platform, arch))

    # Create matrix entries for each needed build
    return [
        {
            "platform": platform,
            "arch": arch,
            # Use the GitHub runner for Windows, because the Depot one is
            # missing a Rust toolchain. On Linux, it's important that the the
            # `python-build` runner matches the `crate-build` runner because of
            # GLIBC version mismatches.
            "runner": find_runner(
                runners, platform, arch, True if platform == "windows" else False
            ),
            "crate_artifact_name": crate_artifact_name(
                platform,
                arch,
            ),
        }
        for platform, arch in needed_builds
        if not platform_filter or platform == platform_filter
    ]


def generate_python_build_matrix_entries(
    config: dict[str, Any],
    runners: dict[str, Any],
    platform_filter: Optional[str] = None,
    label_filters: Optional[dict[str, set[str]]] = None,
) -> list[dict[str, str]]:
    """Generate matrix entries for python builds."""
    matrix_entries = []

    for platform, platform_config in config.items():
        if platform_filter and platform != platform_filter:
            continue

        for target_triple, target_config in platform_config.items():
            add_python_build_entries_for_config(
                matrix_entries,
                target_triple,
                target_config,
                platform,
                runners,
                label_filters.get("directives", set()) if label_filters else set(),
            )

    # Apply label filters if present
    if label_filters:
        matrix_entries = [
            entry
            for entry in matrix_entries
            if should_include_entry(entry, label_filters)
        ]

    return matrix_entries


def find_runner(runners: dict[str, Any], platform: str, arch: str, free: bool) -> str:
    # Find a matching platform first
    match_platform = [
        runner
        for runner in runners
        if runners[runner]["platform"] == platform and runners[runner]["free"] == free
    ]

    # Then, find a matching architecture
    match_arch = [
        runner for runner in match_platform if runners[runner]["arch"] == arch
    ]

    # If there's a matching architecture, use that
    if match_arch:
        return match_arch[0]

    # Otherwise, use the first with a matching platform
    if match_platform:
        return match_platform[0]

    raise RuntimeError(
        f"No runner found for platform {platform!r} and arch {arch!r} with free={free}"
    )


def add_python_build_entries_for_config(
    matrix_entries: list[dict[str, str]],
    target_triple: str,
    config: dict[str, Any],
    platform: str,
    runners: dict[str, Any],
    directives: set[str],
) -> None:
    """Add python build matrix entries for a specific target configuration."""
    python_versions = config["python_versions"]
    build_options = config["build_options"]
    arch = config["arch"]
    runner = find_runner(runners, platform, arch, False)

    # Create base entry that will be used for all variants
    base_entry = {
        "arch": arch,
        "target_triple": target_triple,
        "platform": platform,
        "runner": runner,
        # If `run` is in the config, use that — otherwise, default to if the
        # runner architecture matches the build architecture
        "run": str(config.get("run", runners[runner]["arch"] == arch)).lower(),
        # Use the crate artifact built for the runner's architecture
        "crate_artifact_name": crate_artifact_name(platform, runners[runner]["arch"]),
    }

    # Add optional fields if they exist
    if "arch_variant" in config:
        base_entry["arch_variant"] = config["arch_variant"]
    if "libc" in config:
        base_entry["libc"] = config["libc"]
    if "vcvars" in config:
        base_entry["vcvars"] = config["vcvars"]

    if "dry-run" in directives:
        base_entry["dry-run"] = "true"

    # Process regular build options
    for python_version in python_versions:
        for build_option in build_options:
            entry = base_entry.copy()
            entry.update(
                {
                    "python": python_version,
                    "build_options": build_option,
                }
            )
            matrix_entries.append(entry)

    # Process conditional build options (e.g., freethreaded)
    for conditional in config.get("build_options_conditional", []):
        min_version = conditional["minimum-python-version"]
        for python_version in python_versions:
            if not meets_conditional_version(python_version, min_version):
                continue

            for build_option in conditional["options"]:
                entry = base_entry.copy()
                entry.update(
                    {
                        "python": python_version,
                        "build_options": build_option,
                    }
                )
                matrix_entries.append(entry)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a JSON matrix for building distributions in CI"
    )
    parser.add_argument(
        "--platform",
        choices=["darwin", "linux", "windows"],
        help="Filter matrix entries by platform",
    )
    parser.add_argument(
        "--max-shards",
        type=int,
        default=0,
        help="The maximum number of shards allowed; set to zero to disable ",
    )
    parser.add_argument(
        "--labels",
        help="Comma-separated list of labels to filter by (e.g., 'platform:darwin,python:3.13,build:debug'), all must match.",
    )
    parser.add_argument(
        "--free-runners",
        action="store_true",
        help="If only free runners should be used.",
    )
    parser.add_argument(
        "--force-crate-build",
        action="store_true",
        help="Force crate builds to be included even without python builds.",
    )
    parser.add_argument(
        "--matrix-type",
        choices=["python-build", "docker-build", "crate-build", "all"],
        default="all",
        help="Which matrix types to generate (default: all)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    labels = parse_labels(args.labels)

    with open(CI_TARGETS_YAML, "r") as f:
        config = yaml.safe_load(f)

    with open(CI_RUNNERS_YAML, "r") as f:
        runners = yaml.safe_load(f)

    # If only free runners are allowed, reduce to a subset
    if args.free_runners:
        runners = {
            runner: runner_config
            for runner, runner_config in runners.items()
            if runner_config.get("free")
        }

    result = {}

    # Generate python build entries
    python_entries = generate_python_build_matrix_entries(
        config,
        runners,
        args.platform,
        labels,
    )

    # Output python-build matrix if requested
    if args.matrix_type in ["python-build", "all"]:
        if args.max_shards:
            python_build_matrix = {}
            shards = (len(python_entries) // CI_MATRIX_SIZE_LIMIT) + 1
            if shards > args.max_shards:
                print(
                    f"error: python-build matrix of size {len(python_entries)} requires {shards} shards, but the maximum is {args.max_shards}; consider increasing `--max-shards`",
                    file=sys.stderr,
                )
                sys.exit(1)
            for shard in range(args.max_shards):
                shard_entries = python_entries[
                    shard * CI_MATRIX_SIZE_LIMIT : (shard + 1) * CI_MATRIX_SIZE_LIMIT
                ]
                python_build_matrix[str(shard)] = {"include": shard_entries}
            result["python-build"] = python_build_matrix
        else:
            if len(python_entries) > CI_MATRIX_SIZE_LIMIT:
                print(
                    f"warning: python-build matrix of size {len(python_entries)} exceeds limit of {CI_MATRIX_SIZE_LIMIT} but sharding is not enabled; consider setting `--max-shards`",
                    file=sys.stderr,
                )
            result["python-build"] = {"include": python_entries}

    # Generate docker-build matrix if requested
    # Only include docker builds if there are Linux python builds
    if args.matrix_type in ["docker-build", "all"]:
        # Check if we have any Linux python builds
        has_linux_builds = any(
            entry.get("platform") == "linux" for entry in python_entries
        )

        # If no platform filter or explicitly requesting docker-build only, include docker builds
        # Otherwise, only include if there are Linux python builds
        if args.matrix_type == "docker-build" or has_linux_builds:
            docker_entries = generate_docker_matrix_entries(
                runners,
                args.platform,
            )
            result["docker-build"] = {"include": docker_entries}

    # Generate crate-build matrix if requested
    if args.matrix_type in ["crate-build", "all"]:
        crate_entries = generate_crate_build_matrix_entries(
            python_entries,
            runners,
            config,
            args.force_crate_build,
            args.platform,
        )
        result["crate-build"] = {"include": crate_entries}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
