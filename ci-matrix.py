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
from typing import Any

import yaml
from packaging.version import Version

CI_TARGETS_YAML = "ci-targets.yaml"
CI_RUNNERS_YAML = "ci-runners.yaml"
PR_TARGETS_YAML = "pr-targets.yaml"
CI_EXTRA_SKIP_LABELS = ["documentation"]
CI_MATRIX_SIZE_LIMIT = 256  # The maximum size of a matrix in GitHub Actions


# Docker images for building toolchains and dependencies
DOCKER_BUILD_IMAGES = [
    {"name": "build", "arch": "x86_64"},
    {"name": "build.cross", "arch": "x86_64"},
    {"name": "build.cross-riscv64", "arch": "x86_64"},
    {"name": "build.debian9", "arch": "aarch64"},
    {"name": "gcc", "arch": "x86_64"},
    {"name": "gcc.debian9", "arch": "aarch64"},
]


def crate_artifact_name(platform: str, arch: str) -> str:
    return f"crate-{platform}-{arch}"


def meets_conditional_version(version: str, min_version: str) -> bool:
    return Version(version) >= Version(min_version)


def parse_labels(labels: str | None) -> dict[str, set[str]]:
    """Parse labels into a dict of category -> set of values."""
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


def get_all_build_options(ci_config: dict[str, Any], target_triple: str) -> list[str]:
    """Get all build options (including conditional) for a target from ci-targets.yaml."""
    for _platform, platform_config in ci_config.items():
        if target_triple in platform_config:
            config = platform_config[target_triple]
            options = list(config["build_options"])
            for conditional in config.get("build_options_conditional", []):
                options.extend(conditional["options"])
            return options
    raise KeyError(f"Target triple {target_triple!r} not found in ci-targets.yaml")


def find_target_platform(ci_config: dict[str, Any], target_triple: str) -> str:
    """Find which platform a target triple belongs to in ci-targets.yaml."""
    for platform, platform_config in ci_config.items():
        if target_triple in platform_config:
            return platform
    raise KeyError(f"Target triple {target_triple!r} not found in ci-targets.yaml")


def get_default_target_patterns(
    ci_config: dict[str, Any], pr_config: dict[str, Any]
) -> list[dict[str, str | None]]:
    patterns = []

    for triple in pr_config["targets"]:
        platform = find_target_platform(ci_config, triple)
        config = ci_config[platform][triple]
        patterns.append(
            {
                "platform": platform,
                "arch": config["arch"],
                "arch_variant": config.get("arch_variant"),
                "libc": config.get("libc"),
            }
        )

    return patterns


def get_default_build_options(
    ci_config: dict[str, Any], pr_config: dict[str, Any], target_triple: str
) -> list[str]:
    if target_triple in pr_config["targets"]:
        return list(pr_config["targets"][target_triple]["build_options"])

    platform = find_target_platform(ci_config, target_triple)
    config = ci_config[platform][target_triple]
    return [config["build_options"][-1]]


def matches_default_pattern(
    target_platform: str,
    target_config: dict[str, Any],
    pattern: dict[str, str | None],
    expand_platform: bool,
    expand_arch: bool,
    expand_libc: bool,
) -> bool:
    if not expand_platform and target_platform != pattern["platform"]:
        return False

    if not expand_arch:
        if target_config["arch"] != pattern["arch"]:
            return False
        if target_config.get("arch_variant") != pattern["arch_variant"]:
            return False

    if not expand_libc and target_config.get("libc") != pattern["libc"]:
        return False

    return True


def resolve_pr_targets(
    ci_config: dict[str, Any],
    pr_config: dict[str, Any],
    labels: dict[str, set[str]],
) -> dict[str, Any]:
    """Resolve PR targets from labels."""
    expand_platform = "all" in labels.get("platform", set())
    expand_arch = "all" in labels.get("arch", set())
    expand_libc = "all" in labels.get("libc", set())
    expand_python = "all" in labels.get("python", set())
    expand_build = "all" in labels.get("build", set())

    platform_filters = labels.get("platform", set()) - {"all"}
    arch_filters = labels.get("arch", set()) - {"all"}
    libc_filters = labels.get("libc", set()) - {"all"}
    python_filters = labels.get("python", set()) - {"all"}
    build_filters = labels.get("build", set()) - {"all"}

    if expand_platform or expand_arch or expand_libc:
        source_triples = {}
        for platform, platform_config in ci_config.items():
            for triple, config in platform_config.items():
                source_triples[triple] = (platform, config)
    else:
        source_triples = {}
        for triple in pr_config["targets"]:
            platform = find_target_platform(ci_config, triple)
            source_triples[triple] = (platform, ci_config[platform][triple])

    default_patterns = get_default_target_patterns(ci_config, pr_config)
    result: dict[str, dict[str, Any]] = {}
    pr_default_version = pr_config["python_version"]

    for triple, (platform, ci_target_config) in source_triples.items():
        if expand_platform or expand_arch or expand_libc:
            if not any(
                matches_default_pattern(
                    platform,
                    ci_target_config,
                    pattern,
                    expand_platform,
                    expand_arch,
                    expand_libc,
                )
                for pattern in default_patterns
            ):
                continue

        # Apply label filters.
        if platform_filters and platform not in platform_filters:
            continue
        if arch_filters and ci_target_config["arch"] not in arch_filters:
            continue
        if libc_filters and ci_target_config.get("libc") not in libc_filters:
            continue

        if expand_python:
            python_versions = list(ci_target_config["python_versions"])
        elif python_filters:
            python_versions = [
                version
                for version in sorted(python_filters)
                if version in ci_target_config["python_versions"]
            ]
        else:
            python_versions = [pr_default_version]

        if not python_versions:
            continue

        if expand_build:
            build_options = list(ci_target_config["build_options"])
            build_options_conditional = ci_target_config.get(
                "build_options_conditional", []
            )
        elif build_filters:
            all_build_options = set(get_all_build_options(ci_config, triple))
            build_options = [
                option
                for option in sorted(build_filters)
                if option in all_build_options
            ]
            build_options_conditional = []
        else:
            build_options = get_default_build_options(ci_config, pr_config, triple)
            build_options_conditional = []

        if not build_options and not build_options_conditional:
            continue

        target_config = dict(ci_target_config)
        target_config["python_versions"] = python_versions
        target_config["build_options"] = build_options
        target_config["build_options_conditional"] = build_options_conditional

        result.setdefault(platform, {})[triple] = target_config

    return result


def generate_docker_matrix_entries(
    runners: dict[str, Any],
    python_entries: list[dict[str, str]],
    platform_filter: str | None = None,
) -> list[dict[str, str]]:
    """Generate matrix entries for Docker image builds."""
    if platform_filter and platform_filter != "linux":
        return []

    needed_archs = {
        runners[entry["runner"]]["arch"]
        for entry in python_entries
        if entry.get("platform") == "linux"
    }

    matrix_entries = []
    for image in DOCKER_BUILD_IMAGES:
        if image["arch"] not in needed_archs:
            continue

        # Find appropriate runner for Linux platform with the specified architecture.
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
    platform_filter: str | None = None,
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
    platform_filter: str | None = None,
    label_filters: dict[str, set[str]] | None = None,
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


def create_python_build_entry(
    base_entry: dict[str, Any],
    python_version: str,
    build_option: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    entry = base_entry.copy()
    entry.update(
        {
            "python": python_version,
            "build_options": build_option,
        }
    )
    if "vs_version_override_conditional" in config:
        conditional = config["vs_version_override_conditional"]
        min_version = conditional["minimum-python-version"]
        if meets_conditional_version(python_version, min_version):
            entry["vs_version"] = conditional["vs_version"]
    # TODO remove once VS 2026 is available in 'standard' runnners
    if entry.get("vs_version") == "2026":
        entry["runner"] = "windows-2025-vs2026"
    return entry


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
    if "vs_version" in config:
        base_entry["vs_version"] = config["vs_version"]

    if "dry-run" in directives:
        base_entry["dry-run"] = "true"

    # Process regular build options
    for python_version in python_versions:
        for build_option in build_options:
            entry = create_python_build_entry(
                base_entry, python_version, build_option, config
            )
            matrix_entries.append(entry)

    # Process conditional build options (e.g., freethreaded)
    for conditional in config.get("build_options_conditional", []):
        min_version = conditional["minimum-python-version"]
        for python_version in python_versions:
            if not meets_conditional_version(python_version, min_version):
                continue

            for build_option in conditional["options"]:
                entry = create_python_build_entry(
                    base_entry, python_version, build_option, config
                )
                matrix_entries.append(entry)


def validate_pr_targets(ci_config: dict[str, Any], pr_config: dict[str, Any]) -> None:
    """Validate that all targets in pr-targets.yaml exist in ci-targets.yaml."""
    all_triples = set()
    for platform_config in ci_config.values():
        all_triples.update(platform_config.keys())

    for triple in pr_config["targets"]:
        if triple not in all_triples:
            print(
                f"error: target triple {triple!r} in {PR_TARGETS_YAML} not found in {CI_TARGETS_YAML}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate that each build option listed is valid for the target
        all_options = set(get_all_build_options(ci_config, triple))
        for option in pr_config["targets"][triple]["build_options"]:
            if option not in all_options:
                print(
                    f"error: build option {option!r} for {triple} in {PR_TARGETS_YAML} "
                    f"not found in {CI_TARGETS_YAML} (valid: {sorted(all_options)})",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Validate that the default python version exists in ci-targets.yaml
    default_version = pr_config["python_version"]
    for triple in pr_config["targets"]:
        platform = find_target_platform(ci_config, triple)
        ci_versions = ci_config[platform][triple]["python_versions"]
        if default_version not in ci_versions:
            print(
                f"error: python version {default_version!r} in {PR_TARGETS_YAML} "
                f"not available for {triple} in {CI_TARGETS_YAML} (valid: {ci_versions})",
                file=sys.stderr,
            )
            sys.exit(1)


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
        help="Comma-separated list of labels to filter by (e.g., 'platform:linux,python:3.13')",
    )
    parser.add_argument(
        "--event",
        choices=["pull_request", "push"],
        help="The GitHub event type. When 'pull_request', uses pr-targets.yaml for the default subset.",
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

    with open(CI_TARGETS_YAML) as f:
        ci_config = yaml.safe_load(f)

    with open(CI_RUNNERS_YAML) as f:
        runners = yaml.safe_load(f)

    # If only free runners are allowed, reduce to a subset
    if args.free_runners:
        runners = {
            runner: runner_config
            for runner, runner_config in runners.items()
            if runner_config.get("free")
        }

    # Check for skip directive
    if labels.get("directives") and "skip" in labels["directives"]:
        # Emit empty matrices
        result = {}
        if args.matrix_type in ["python-build", "all"]:
            if args.max_shards:
                result["python-build"] = {
                    str(i): {"include": []} for i in range(args.max_shards)
                }
            else:
                result["python-build"] = {"include": []}
        if args.matrix_type in ["docker-build", "all"]:
            result["docker-build"] = {"include": []}
        if args.matrix_type in ["crate-build", "all"]:
            result["crate-build"] = {"include": []}
        print(json.dumps(result))
        return

    full_matrix = args.event != "pull_request" or "all-targets" in labels.get(
        "directives", set()
    )

    if full_matrix:
        config = ci_config
    else:
        with open(PR_TARGETS_YAML) as f:
            pr_config = yaml.safe_load(f)

        validate_pr_targets(ci_config, pr_config)
        config = resolve_pr_targets(ci_config, pr_config, labels)

    result = {}

    # Generate python build entries
    directives = labels.get("directives", set())
    python_entries = generate_python_build_matrix_entries(
        config,
        runners,
        args.platform,
        {"directives": directives} if directives else None,
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
    # Only include docker builds if there are Linux python builds.
    if args.matrix_type in ["docker-build", "all"]:
        # Check if we have any Linux python builds.
        has_linux_builds = any(
            entry.get("platform") == "linux" for entry in python_entries
        )

        # If no platform filter or explicitly requesting docker-build only, include docker builds.
        # Otherwise, only include if there are Linux python builds.
        if args.matrix_type == "docker-build" or has_linux_builds:
            docker_entries = generate_docker_matrix_entries(
                runners,
                python_entries,
                args.platform,
            )
            result["docker-build"] = {"include": docker_entries}

    # Generate crate-build matrix if requested
    if args.matrix_type in ["crate-build", "all"]:
        crate_entries = generate_crate_build_matrix_entries(
            python_entries,
            runners,
            ci_config,  # Use the full target config so --force-crate-build adds all native crate builds.
            args.force_crate_build,
            args.platform,
        )
        result["crate-build"] = {"include": crate_entries}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
