# Python Build Standalone

[![Release](https://img.shields.io/github/v/release/astral-sh/python-build-standalone)](https://github.com/astral-sh/python-build-standalone/releases)

[**Docs**](https://docs.astral.sh/python-build-standalone/) | [**Releases**](https://github.com/astral-sh/python-build-standalone/releases)

Self-contained, portable, high-performance Python distributions.

## Highlights

- [High performance](https://github.com/astral-sh/python-build-standalone/blob/main/BENCHMARKS.md),
  as fast or faster than other CPython distributions.
- Portable, can be installed into any path.
- Self-contained, extension modules and dependencies included.
- Python 3.10-3.15.
- Standard and free-threaded builds.
- Linux, macOS, and Windows.
- Multiple [platforms and architectures](https://docs.astral.sh/python-build-standalone/running/#obtaining-distributions)
  supported.
- Ready to use with [uv](https://docs.astral.sh/uv/) or directly from
  [release archives](https://github.com/astral-sh/python-build-standalone/releases).

Python Build Standalone is maintained by [Astral](https://astral.sh), the team
behind [uv](https://github.com/astral-sh/uv), [ruff](https://github.com/astral-sh/ruff),
and [ty](https://github.com/astral-sh/ty).

## Getting started

The most common way to use these distributions is with
[uv](https://docs.astral.sh/uv/). Run a managed Python installation with:

```shell
uvx --managed-python python
```

Choose a specific Python version or a free-threaded build:

```shell
uvx --managed-python python@3.13
uvx --managed-python python@3.14+freethreaded
```

See the [documentation](https://docs.astral.sh/python-build-standalone/) for more,
including [running distributions](https://docs.astral.sh/python-build-standalone/running/)
and [behavior quirks](https://docs.astral.sh/python-build-standalone/quirks/).

## Downloads

Prebuilt distributions are available on
[GitHub Releases](https://github.com/astral-sh/python-build-standalone/releases).
Choose an archive for your Python version, operating system, and architecture.
Most users should choose an `install_only` archive; `full` archives also contain
build artifacts for creating custom Python distributions.

See [distribution archives](https://docs.astral.sh/python-build-standalone/distributions/)
for details on the available formats.
