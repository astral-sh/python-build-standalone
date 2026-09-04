# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pathlib
import re
import tarfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import IO

import jsonschema
import yaml

from pythonbuild.logging import log

EXTENSION_MODULE_SCHEMA = {
    "type": "object",
    "properties": {
        "build-mode": {"type": "string"},
        "config-c-only": {"type": "boolean"},
        "config-c-only-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "config-c-only": {"type": "boolean"},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["config-c-only"],
            },
        },
        "defines": {"type": "array", "items": {"type": "string"}},
        "defines-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "define": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["define"],
            },
        },
        "disabled-targets": {"type": "array", "items": {"type": "string"}},
        "frameworks": {"type": "array", "items": {"type": "string"}},
        "includes": {"type": "array", "items": {"type": "string"}},
        "includes-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "includes": {"type": "array", "items": {"type": "string"}},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "includes-deps": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
        "links-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "build-mode": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        "linker-args": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "targets": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "minimum-python-version": {"type": "string"},
        "maximum-python-version": {"type": "string"},
        "required-targets": {"type": "array", "items": {"type": "string"}},
        "setup-enabled": {"type": "boolean"},
        "setup-enabled-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["enabled"],
            },
        },
        "sources": {"type": "array", "items": {"type": "string"}},
        "sources-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
                "oneOf": [
                    {
                        "required": ["source"],
                    },
                    {
                        "required": ["sources"],
                    },
                ],
            },
        },
    },
    "additionalProperties": False,
}

EXTENSION_MODULES_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^[a-z0-9_]+$": EXTENSION_MODULE_SCHEMA,
    },
}


# Packages that define tests.
STDLIB_TEST_PACKAGES = {
    "bsddb.test",
    "ctypes.test",
    "distutils.tests",
    "email.test",
    "idlelib.idle_test",
    "json.tests",
    "lib-tk.test",
    "lib2to3.tests",
    "sqlite3.test",
    "test",
    "tkinter.test",
    "unittest.test",
}


def parse_setup_line(line: bytes, python_version: str):
    """Parse a line in a ``Setup.*`` file."""
    if b"#" in line:
        line = line[: line.index(b"#")].rstrip()

    if not line:
        return

    words = line.split()

    extension = words[0].decode("ascii")

    objs = set()
    links = set()
    frameworks = set()

    for i, word in enumerate(words):
        # Arguments looking like C source files are converted to object files.
        if word.endswith(b".c"):
            # Object files are named according to the basename: parent
            # directories they may happen to reside in are stripped out.
            source_path = pathlib.Path(word.decode("ascii"))

            # Python 3.11 changed the path of the object file.
            if meets_python_minimum_version(python_version, "3.11") and b"/" in word:
                obj_path = (
                    pathlib.Path("Modules")
                    / source_path.parent
                    / source_path.with_suffix(".o").name
                )
            else:
                obj_path = pathlib.Path("Modules") / source_path.with_suffix(".o").name

            objs.add(obj_path)

        # Arguments looking like link libraries are converted to library
        # dependencies.
        elif word.startswith(b"-l"):
            links.add(word[2:].decode("ascii"))

        elif word.startswith(b"-hidden-l"):
            links.add(word[len("-hidden-l") :].decode("ascii"))

        elif word == b"-framework":
            frameworks.add(words[i + 1].decode("ascii"))

    return {
        "extension": extension,
        "line": line,
        "posix_obj_paths": objs,
        "links": links,
        "frameworks": frameworks,
        "variant": "default",
    }


def link_for_target(lib: str, target_triple: str) -> str:
    # TODO use -Wl,-hidden-lbz2?
    # TODO use -Wl,--exclude-libs,libfoo.a?

    if "-apple-" in target_triple:
        # The -l:filename syntax doesn't appear to work on Apple.
        # just give the library name and hope it turns out OK.
        if lib.startswith(":lib") and lib.endswith(".a"):
            return f"-Xlinker -hidden-l{lib[4:-2]}"
        else:
            return f"-Xlinker -hidden-l{lib}"
    else:
        return f"-l{lib}"


def meets_python_minimum_version(got: str, wanted: str | dict) -> bool:
    if isinstance(wanted, dict):
        wanted_version: str = wanted.get("minimum-python-version", "1.0")
    else:
        wanted_version = wanted

    parts = got.split(".")
    got_major, got_minor = int(parts[0]), int(parts[1])

    parts = wanted_version.split(".")
    wanted_major, wanted_minor = int(parts[0]), int(parts[1])

    return (got_major, got_minor) >= (wanted_major, wanted_minor)


def meets_python_maximum_version(got: str, wanted: str | dict) -> bool:
    if isinstance(wanted, dict):
        wanted_version: str = wanted.get("maximum-python-version", "100.0")
    else:
        wanted_version = wanted

    parts = got.split(".")
    got_major, got_minor = int(parts[0]), int(parts[1])

    parts = wanted_version.split(".")
    wanted_major, wanted_minor = int(parts[0]), int(parts[1])

    return (got_major, got_minor) <= (wanted_major, wanted_minor)


def _render_setup_local(section_lines: dict[str, list[bytes]]) -> bytes:
    lines = []

    for section, section_content in sorted(section_lines.items()):
        if not section_content:
            continue

        lines.append(b"\n*%s*\n" % section.encode("ascii"))
        lines.extend(section_content)

    lines.append(b"")

    return b"\n".join(lines)


def _render_make_data(extra_cflags: dict[bytes, list[bytes]]) -> bytes:
    lines = []

    for target in sorted(extra_cflags):
        lines.append(
            b"%s: PY_STDMODULE_CFLAGS += %s" % (target, b" ".join(extra_cflags[target]))
        )

    return b"\n".join(lines)


def _parse_setup_stdlib(
    setup_stdlib_lines: Iterable[bytes],
) -> tuple[dict[str, bytes], dict[str, str]]:
    extension_pattern = re.compile(rb"^@MODULE_[A-Z0-9_]+_TRUE@([a-z0-9_]+\s+.*)$")
    module_lines = {}
    module_linkage = {}

    # CPython 3.12+ is configured with MODULE_BUILDTYPE=static.
    section = "static"

    for line in setup_stdlib_lines:
        line = line.rstrip()

        if line == b"*shared*":
            section = "shared"
            continue
        elif line == b"*static*":
            section = "static"
            continue

        if match := extension_pattern.match(line):
            line = match.group(1)
            name = line.split()[0].decode("ascii")
            module_lines[name] = line
            module_linkage[name] = section

    return module_lines, module_linkage


def _parse_setup_bootstrap(setup_bootstrap_lines: Iterable[bytes]) -> dict[str, bytes]:
    extension_pattern = re.compile(rb"^([a-z_]+)\s.*[a-zA-Z/_-]+\.c\b")
    module_lines = {}

    for line in setup_bootstrap_lines:
        if b"#" in line:
            line = line[: line.index(b"#")]

        # There is special `@MODULE_<name>_TRUE@` syntax that gets elided or turned
        # into a comment during Makefile expansion. For now, just pretend it always
        # goes away. This assumption may not be valid in future Python versions. But
        # as of 3.11 only pwd is defined this way.
        if line.startswith(b"@") and line.count(b"@") == 2:
            line = line.split(b"@")[-1]

        line = line.strip()

        if not line:
            continue

        if match := extension_pattern.match(line):
            name = match.group(1).decode("ascii")
            module_lines[name] = line

    return module_lines


def _parse_setup(
    setup_lines: Iterable[bytes],
) -> tuple[set[str], set[str], dict[str, bytes]]:
    variable_pattern = re.compile(rb"^[a-zA-Z_]+\s*=")
    extension_pattern = re.compile(rb"^([a-z_]+)\s.*[a-zA-Z/_-]+\.c\b")
    modules = set()
    enabled_modules = set()
    enabled_lines = {}
    section = "static"

    for line in setup_lines:
        line = line.rstrip()

        if not line:
            continue

        # Looks like a variable assignment.
        if variable_pattern.match(line):
            continue

        # Look for extension syntax before and after comment.
        for index, part in enumerate(line.split(b"#")):
            if match := extension_pattern.match(part):
                name = match.group(1).decode("ascii")
                modules.add(name)

                if index == 0:
                    enabled_modules.add(name)

                break

        # Now look for enabled extensions and stash away the line.
        if line == b"*static*":
            section = "static"
            continue
        elif line == b"*shared*":
            section = "shared"
            continue
        elif line == b"*disabled*":
            section = "disabled"
            continue

        if b"#" in line:
            line = line[: line.index(b"#")].strip()

        if line and section != "disabled":
            enabled_lines[line.split()[0].decode("ascii")] = line

    return modules, enabled_modules, enabled_lines


def _parse_makefile_variables(makefile: bytes) -> dict[str, bytes]:
    """Parse Makefile assignments, including continued and appended values."""
    assignment_pattern = re.compile(rb"^([A-Za-z_][A-Za-z0-9_]*)\s*([+:?]?)=\s*(.*)$")
    variables: dict[str, bytes] = {}

    for line in makefile.replace(b"\\\n", b" ").splitlines():
        if not (match := assignment_pattern.match(line)):
            continue

        name = match.group(1).decode("ascii")
        operator = match.group(2)
        value = match.group(3).strip()

        if operator == b"+" and name in variables:
            variables[name] += b" " + value
        elif operator != b"?" or name not in variables:
            variables[name] = value

    return variables


def _expand_makefile_variables(value: bytes, variables: dict[str, bytes]) -> bytes:
    """Expand simple Makefile variable references in archive and object lists."""
    reference_pattern = re.compile(rb"\$\(([A-Za-z_][A-Za-z0-9_]*)\)")
    expanded: dict[str, bytes] = {}
    expanding: set[str] = set()

    def replace(match: re.Match[bytes]) -> bytes:
        name = match.group(1).decode("ascii")
        if name not in variables:
            return match.group(0)
        if name in expanded:
            return expanded[name]
        if name in expanding:
            raise ValueError("recursive Makefile variable references")
        expanding.add(name)
        try:
            result = reference_pattern.sub(replace, variables[name])
        finally:
            expanding.remove(name)
        expanded[name] = result
        return result

    return reference_pattern.sub(replace, value)


def _configured_setup_lines(
    setup_files: Iterable[bytes], python_version: str
) -> dict[str, bytes]:
    """Return a mapping between module names and lines, respecting makesetup's first-rule precedence."""
    setup_lines: dict[str, bytes] = {}
    for setup_file in setup_files:
        _, _, current_setup_lines = _parse_setup(setup_file.splitlines())
        for name, line in current_setup_lines.items():
            parsed = parse_setup_line(line, python_version)
            if parsed and parsed["posix_obj_paths"]:
                setup_lines.setdefault(name, line)
    return setup_lines


def _internal_archive_objects(makefile: bytes) -> dict[str, set[pathlib.Path]]:
    """Map CPython's internal static archives to their constituent object files."""
    variables = _parse_makefile_variables(makefile)
    archives = {}

    for name, value in variables.items():
        if name.endswith("_LIB_STATIC"):
            object_variable = f"{name.removesuffix('_LIB_STATIC')}_OBJS"
        elif name.endswith("_A"):
            object_variable = f"{name.removesuffix('_A')}_OBJS"
        else:
            continue

        if object_variable not in variables:
            continue

        archive = _expand_makefile_variables(value, variables).decode("ascii")
        objects = _expand_makefile_variables(variables[object_variable], variables)
        archives[archive] = {
            pathlib.Path(path.decode("ascii"))
            for path in objects.split()
            if path.endswith(b".o")
        }

    return archives


@dataclass
class ExtensionInfo:
    """Build-artifact metadata consumed when generating PYTHON.json."""

    init_fn: str
    in_core: bool
    setup_line: bytes
    # "static", "shared", None if in core
    build_mode: str | None = None
    # Object files linked indirectly through CPython's internal static archives.
    # For example via libHacl_HMAC.a
    archive_obj_paths: set[pathlib.Path] = field(default_factory=set)
    required_targets: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "init_fn": self.init_fn,
            "in_core": self.in_core,
            "setup_line": self.setup_line,
        }
        if self.required_targets is not None:
            metadata["required-targets"] = self.required_targets
        if self.build_mode is not None:
            metadata["build-mode"] = self.build_mode
            metadata["archive_obj_paths"] = self.archive_obj_paths
        return metadata


def configured_extension_modules(
    python_version: str,
    setup_files: Iterable[bytes],
    config_c: bytes,
    makefile: bytes,
    config_vars: dict[str, str],
    extension_modules: dict[str, dict],
) -> dict[str, dict]:
    """Derive extension metadata from built CPython artifacts."""
    built_modules = set(config_vars["MODBUILT_NAMES"].split())
    shared_modules = set(config_vars["MODSHARED_NAMES"].split())
    builtin_modules = parse_config_c(config_c.decode("utf-8"))
    module_names = built_modules | set(builtin_modules)

    # Validate that all modules have YAML metadata and were built
    if missing := module_names - set(extension_modules):
        raise ValueError(f"modules lack metadata: {', '.join(missing)}")
    if missing := set(extension_modules) - module_names:
        raise ValueError(f"modules were not built: {', '.join(missing)}")

    setup_lines = _configured_setup_lines(setup_files, python_version)
    archive_objects = _internal_archive_objects(makefile)
    extensions: dict[str, ExtensionInfo] = {}

    for name in sorted(module_names):
        policy = extension_modules[name]
        in_core = name not in built_modules
        extension_info = ExtensionInfo(
            init_fn=builtin_modules.get(name, f"PyInit_{name}"),
            in_core=in_core,
            setup_line=name.encode("ascii"),
            required_targets=policy.get("required-targets"),
        )

        if in_core:
            extensions[name] = extension_info
            continue

        if name not in setup_lines:
            raise ValueError(f"configured extension {name} has no Modules/Setup rule")

        build_mode = "shared" if name in shared_modules else "static"
        expected_build_mode = policy.get("build-mode")
        if build_mode != expected_build_mode:
            raise ValueError(
                f"extension {name} built as {build_mode}; expected {expected_build_mode}"
            )

        setup_line = setup_lines[name]
        linker_flags = config_vars.get(f"MODULE_{name.upper()}_LDFLAGS", "")
        if linker_flags:
            setup_line += f" {linker_flags}".encode("ascii")

        archive_obj_paths: set[pathlib.Path] = set()
        for word in setup_line.split():
            if word.endswith(b".a") and not word.startswith(b"-"):
                archive = word.decode("ascii")
                if archive not in archive_objects:
                    raise ValueError(
                        f"extension {name} references unknown static archive {archive}"
                    )
                archive_obj_paths.update(archive_objects[archive])

        extension_info.setup_line = setup_line
        extension_info.build_mode = build_mode
        extension_info.archive_obj_paths = archive_obj_paths
        extensions[name] = extension_info

    return {name: metadata.to_dict() for name, metadata in extensions.items()}


@dataclass
class CPythonModuleInfo:
    # Maps extension names to lines in Modules/Setup.stdlib.in
    stdlib_lines: dict[str, bytes]
    # Maps extension names to default linkage in Setup.stdlib.in
    stdlib_linkage: dict[str, str]
    # Maps extension names to uncommented lines in Modules/{Setup,Setup.bootstrap.in}
    setup_lines: dict[str, bytes]
    # Modules enabled by Setup or Setup.bootstrap.in
    setup_enabled: set[str]
    # Maps extension names to init function name defined in Modules/config.c.in
    config_c_extensions: dict[str, str]
    # Names of all modules declared in Setup.stdlib.in, Setup, Setup.bootstrap or config.c
    module_names: set[str]


@dataclass
class ExtensionClassification:
    # Extension modules that are available but disabled for the target or build
    disabled: set[str]
    # Not applicable for the Python version
    ignored: set[str]
    # Enabled via Modules/{Setup,Setup.bootstrap.in}
    setup_enabled: set[str]
    # Declared in Modules/config.c.in, not an external extension module
    config_c_only: set[str]


def _parse_cpython_module_info(
    cpython_source_archive: pathlib.Path,
    python_version: str,
    read_setup_stdlib: bool,
) -> CPythonModuleInfo:
    """Parse extension module information from the CPython source archive."""
    with tarfile.open(str(cpython_source_archive)) as source_archive:

        def extract_file(filename: str) -> IO[bytes]:
            archive_path = f"Python-{python_version}/Modules/{filename}"
            file = source_archive.extractfile(archive_path)
            if file is None:
                raise ValueError(f"not a regular file: {archive_path}")
            return file

        if read_setup_stdlib:
            with extract_file("Setup.stdlib.in") as stdlib_file:
                stdlib_lines, stdlib_linkage = _parse_setup_stdlib(stdlib_file)
        else:
            stdlib_lines, stdlib_linkage = {}, {}

        with extract_file("Setup") as setup_file:
            setup_modules, setup_enabled, setup_lines = _parse_setup(setup_file)

        try:
            bootstrap_file = extract_file("Setup.bootstrap.in")
        except KeyError:
            bootstrap_lines = {}
        else:
            with bootstrap_file:
                bootstrap_lines = _parse_setup_bootstrap(bootstrap_file)

        with extract_file("config.c.in") as config_file:
            config_c_extensions = parse_config_c(config_file.read().decode("utf-8"))

    setup_lines = bootstrap_lines | setup_lines
    setup_enabled = set(bootstrap_lines) | setup_enabled
    module_names = setup_modules.union(
        stdlib_lines, bootstrap_lines, config_c_extensions
    )

    return CPythonModuleInfo(
        stdlib_lines=stdlib_lines,
        stdlib_linkage=stdlib_linkage,
        setup_lines=setup_lines,
        setup_enabled=setup_enabled,
        config_c_extensions=config_c_extensions,
        module_names=module_names,
    )


def _classify_extension_modules(
    extension_modules: dict[str, dict],
    python_version: str,
    target_triple: str,
    build_options: set[str],
) -> ExtensionClassification:
    """Classify extension modules based on the YAML based metadata."""
    disabled = set()
    ignored = set()
    setup_enabled = set()
    config_c_only = set()

    for name, info in sorted(extension_modules.items()):
        supported_build_modes = (None, "shared", "static", "shared-or-disabled")
        if info.get("build-mode") not in supported_build_modes:
            raise Exception("unsupported build-mode for extension module %s" % name)

        python_min_match = meets_python_minimum_version(python_version, info)
        python_max_match = meets_python_maximum_version(python_version, info)
        if not (python_min_match and python_max_match):
            log(f"ignoring extension module {name} because Python version incompatible")
            ignored.add(name)
            continue

        if targets := info.get("disabled-targets"):
            if any(re.match(p, target_triple) for p in targets):
                log(
                    f"disabling extension module {name} because disabled for this target triple"
                )
                disabled.add(name)

        # If the extension is to be built as shared but this isn't possible due to
        # a static build, disable the extension.
        if info.get("build-mode") == "shared-or-disabled" and "static" in build_options:
            disabled.add(name)

        if info.get("setup-enabled", False):
            setup_enabled.add(name)

        for entry in info.get("setup-enabled-conditional", []):
            min_match = meets_python_minimum_version(python_version, entry)
            max_match = meets_python_maximum_version(python_version, entry)
            if entry.get("enabled", False) and (min_match and max_match):
                setup_enabled.add(name)

        if info.get("config-c-only"):
            config_c_only.add(name)

        for entry in info.get("config-c-only-conditional", []):
            min_match = meets_python_minimum_version(python_version, entry)
            max_match = meets_python_maximum_version(python_version, entry)
            if entry.get("config-c-only", False) and (min_match and max_match):
                config_c_only.add(name)

    return ExtensionClassification(
        disabled=disabled,
        ignored=ignored,
        setup_enabled=setup_enabled,
        config_c_only=config_c_only,
    )


def _validate_extension_modules(
    extension_modules: dict[str, dict],
    source: CPythonModuleInfo,
    classification: ExtensionClassification,
) -> None:
    # Comparing our metadata with CPython's declarations makes it easier to
    # catch subtle bugs caused by extension metadata getting out of sync.
    missing = source.module_names - set(extension_modules.keys())

    if missing:
        raise Exception(
            "missing extension modules from YAML: %s" % ", ".join(sorted(missing))
        )

    missing = source.setup_enabled - classification.setup_enabled
    if missing:
        raise Exception(
            "Setup enabled extensions missing YAML setup-enabled annotation: %s"
            % ", ".join(sorted(missing))
        )

    extra = classification.setup_enabled - source.setup_enabled
    if extra:
        raise Exception(
            "YAML setup-enabled extensions not present in Setup: %s"
            % ", ".join(sorted(extra))
        )

    if missing := set(source.config_c_extensions) - classification.config_c_only:
        raise Exception(
            "config.c.in extensions missing YAML config-c-only annotation: %s"
            % ", ".join(sorted(missing))
        )

    if extra := classification.config_c_only - set(source.config_c_extensions):
        raise Exception(
            "YAML config-c-only extensions not present in config.c.in: %s"
            % ", ".join(sorted(extra))
        )


def _matches_extension_condition(
    condition: dict,
    python_version: str,
    target_triple: str,
) -> bool:
    if targets := condition.get("targets", []):
        target_match = any(re.match(pattern, target_triple) for pattern in targets)
    else:
        target_match = True

    python_min_match = meets_python_minimum_version(python_version, condition)
    python_max_match = meets_python_maximum_version(python_version, condition)

    return target_match and python_min_match and python_max_match


def _build_yaml_setup_line(
    name: str,
    info: dict,
    python_version: str,
    target_triple: str,
    build_mode: str,
) -> tuple[bytes, dict[bytes, list[bytes]]]:
    line = name

    for source in info.get("sources", []):
        line += " %s" % source

    for entry in info.get("sources-conditional", []):
        condition_matches = _matches_extension_condition(
            entry,
            python_version,
            target_triple,
        )

        if required_build_mode := entry.get("build-mode"):
            build_mode_match = build_mode == required_build_mode
        else:
            build_mode_match = True

        if condition_matches and build_mode_match:
            if source := entry.get("source"):
                line += f" {source}"
            for source in entry.get("sources", []):
                line += f" {source}"

    for define in info.get("defines", []):
        line += f" -D{define}"

    for entry in info.get("defines-conditional", []):
        if _matches_extension_condition(entry, python_version, target_triple):
            line += f" -D{entry['define']}"

    for path in info.get("includes", []):
        line += f" -I{path}"

    for entry in info.get("includes-conditional", []):
        if _matches_extension_condition(entry, python_version, target_triple):
            # TODO: Change to `include` and drop support for `path`
            if include := entry.get("path"):
                line += f" -I{include}"
            for include in entry.get("includes", []):
                line += f" -I{include}"

    for path in info.get("includes-deps", []):
        # Includes are added to global search path.
        if "-apple-" in target_triple:
            continue

        line += f" -I/tools/deps/{path}"

    for lib in info.get("links", []):
        line += " %s" % link_for_target(lib, target_triple)

    for entry in info.get("links-conditional", []):
        if _matches_extension_condition(entry, python_version, target_triple):
            line += " %s" % link_for_target(entry["name"], target_triple)

    if "-apple-" in target_triple:
        for framework in info.get("frameworks", []):
            line += f" -framework {framework}"

    for entry in info.get("linker-args", []):
        if any(re.match(p, target_triple) for p in entry["targets"]):
            for arg in entry["args"]:
                line += f" -Xlinker {arg}"

    setup_line = line.encode("ascii")
    define_pattern = re.compile(rb"-D[^=]+=[^\s]+")

    # This extra parse is a holder from older code and could likely be
    # factored away.
    parsed = parse_setup_line(setup_line, python_version=python_version)

    if not parsed:
        raise Exception("we should always parse a setup line we generated")

    # makesetup interprets lines containing = as configuration options. Move
    # -Dname=value defines into Makefile overrides for legacy Python builds.
    module_cflags: defaultdict[bytes, list[bytes]] = defaultdict(list)
    for match in define_pattern.finditer(parsed["line"]):
        for obj_path in sorted(parsed["posix_obj_paths"]):
            module_cflags[bytes(obj_path)].append(match.group(0))

    setup_line = define_pattern.sub(b"", setup_line)

    if b"=" in setup_line:
        raise Exception(
            "= appears in EXTRA_MODULES line; will confuse "
            "makesetup: %s" % setup_line.decode("utf-8")
        )

    return setup_line, module_cflags


def _determine_module_linkage(info: dict, build_options: set[str]) -> str:
    # Fully static builds override the configured per-module linkage.
    build_mode = (
        "static" if "static" in build_options else info.get("build-mode", "static")
    )

    # shared-or-disabled modules have already been disabled for static builds.
    return "shared" if build_mode == "shared-or-disabled" else build_mode


def _init_extension_metadata(
    name: str, info: dict, module_info: CPythonModuleInfo
) -> dict:
    metadata = dict(info)

    # The initialization function is usually PyInit_{extension}. But some
    # config.c.in extensions don't follow this convention!
    if name in module_info.config_c_extensions:
        metadata["init_fn"] = module_info.config_c_extensions[name]
        metadata["in_core"] = True
    else:
        metadata["init_fn"] = f"PyInit_{name}"
        metadata["in_core"] = False

    return metadata


def derive_setup_local(
    cpython_source_archive: pathlib.Path,
    python_version: str,
    target_triple: str,
    build_options: set[str],
    extension_modules: dict[str, dict],
):
    """Derive the content of the Modules/Setup.local file."""

    use_setup_stdlib = meets_python_minimum_version(python_version, "3.12")

    # Validate that the YAML based metadata is in sync with the various files declaring extension
    # modules in the Python source archive.
    classification = _classify_extension_modules(
        extension_modules, python_version, target_triple, build_options
    )
    module_info = _parse_cpython_module_info(
        cpython_source_archive, python_version, use_setup_stdlib
    )
    _validate_extension_modules(extension_modules, module_info, classification)

    # Generate a Setup.local file.
    # Python 3.12+ builds extensions from Setup.stdlib using configure-derived
    # compiler and linker flags. Setup.local only disables modules or overrides
    # linkage that differs from Setup.stdlib.
    # Python 3.10 and 3.11 use YAML-derived compilation rules for every extension.
    section_lines: dict[str, list[bytes]] = {
        "disabled": [],
        "shared": [],
        "static": [],
    }

    # makesetup parses lines with = as extra config options. There appears
    # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
    # around this by producing a Makefile supplement that overrides the build
    # rules for certain targets to include these missing values.
    extra_cflags: defaultdict[bytes, list[bytes]] = defaultdict(list)

    enabled_extensions = {}

    for name, info in sorted(extension_modules.items()):
        if name in classification.ignored:
            continue

        if name in classification.disabled:
            section_lines["disabled"].append(name.encode("ascii"))
            continue

        enabled_extensions[name] = _init_extension_metadata(name, info, module_info)

        # config.c.in only extensions are part of core object files. There is
        # nothing else to process.
        if name in classification.config_c_only:
            log(f"extension {name} enabled through config.c")
            enabled_extensions[name]["setup_line"] = name.encode("ascii")
            continue

        section = _determine_module_linkage(info, build_options)
        enabled_extensions[name]["build-mode"] = section

        # Presumably this means the extension comes from the distribution's
        # Setup. Lack of sources means we don't need to derive a Setup.local
        # line.
        if "sources" not in info and "sources-conditional" not in info:
            if name not in module_info.setup_lines:
                raise Exception(
                    f"found a sourceless extension ({name}) with no Setup entry"
                )

            log(f"extension {name} enabled through distribution's Modules/Setup file")

            # Preserve the Setup line for Python 3.10/3.11 metadata generation.
            # Python 3.12+ reconstructs metadata from configured build files.
            enabled_extensions[name]["setup_line"] = module_info.setup_lines[name]
            continue

        if use_setup_stdlib:  # 3.12+
            if name in module_info.stdlib_lines:
                log(f"extension {name} being configured via Modules/Setup.stdlib")
            else:
                log(f"extension {name} being configured via Modules/Setup.bootstrap")

            if section == module_info.stdlib_linkage.get(name, "static"):
                continue

            if name not in module_info.stdlib_lines:
                raise Exception(
                    f"{section} extension {name} has no Modules/Setup.stdlib.in entry"
                )

            # Inherit the MODULE_<name>_CFLAGS/LDFLAGS produced by configure.
            section_lines[section].append(module_info.stdlib_lines[name])
        else:  # 3.10 and 3.11
            log(f"extension {name} being configured via YAML metadata")
            line, module_cflags = _build_yaml_setup_line(
                name,
                info,
                python_version,
                target_triple,
                section,
            )
            for obj_path, flags in module_cflags.items():
                extra_cflags[obj_path].extend(flags)
            enabled_extensions[name]["setup_line"] = line
            section_lines[section].append(line)

    return {
        "extensions": enabled_extensions,
        "setup_local": _render_setup_local(section_lines),
        "make_data": _render_make_data(extra_cflags),  # Empty in 3.12+
    }


RE_INITTAB_ENTRY = re.compile(r'\{"([^"]+)", ([^\}]+)\},')


def parse_config_c(s: str):
    """Parse the contents of a config.c file.

    The file defines external symbols for module init functions and the
    mapping of module name to module initializer function.
    """

    # Some config.c files have #ifdef. We don't care about those because
    # in all cases the condition is true.

    extensions = {}

    seen_inittab = False

    for line in s.splitlines():
        if line.startswith("struct _inittab"):
            seen_inittab = True

        if not seen_inittab:
            continue

        if "/* Sentinel */" in line:
            break

        m = RE_INITTAB_ENTRY.search(line)

        if m:
            extensions[m.group(1)] = m.group(2)

    return extensions


def extension_modules_config(yaml_path: pathlib.Path):
    """Loads the extension-modules.yml file."""
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=yaml.SafeLoader)

    jsonschema.validate(data, EXTENSION_MODULES_SCHEMA)

    return data
