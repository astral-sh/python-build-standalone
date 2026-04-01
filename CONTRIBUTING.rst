============
Contributing
============

Building distributions
======================

See the [documentation](https://gregoryszorc.com/docs/python-build-standalone/main/building.html)
for instructions on building distributions locally.

Pull request labels
===================
By default, pull requests build a small subset of targets defined in
``ci-defaults.yaml`` under ``pull_request``. Pushes to ``main`` build the full
matrix from ``ci-targets.yaml``.

Pull request labels can be used to change what CI builds:

* ``platform:<value>`` filters the selected targets by platform.
* ``arch:<value>`` filters the selected targets by architecture.
* ``libc:<value>`` filters the selected targets by libc.
* ``python:<value>`` filters the selected Python versions.
* ``build:<value>`` filters the selected build options by component.

The ``:all`` labels expand only their own dimension:

* ``platform:all`` expands the selected platforms.
* ``arch:all`` expands the selected architectures.
* ``libc:all`` expands the selected libc variants.
* ``python:all`` expands the selected Python versions.
* ``build:all`` expands the selected build options.

Use ``ci:all-targets`` to build the full matrix from ``ci-targets.yaml``.

Examples:

* ``platform:linux`` builds only the Linux targets from ``ci-defaults.yaml``.
* ``python:3.13`` builds the default targets with Python 3.13.
* ``build:pgo`` builds the selected targets whose build options include ``pgo``.
* ``platform:linux,arch:all,libc:all,python:all,build:all`` builds the full
  Linux matrix.

To bypass CI entirely for changes that do not affect the build, use the
``ci:skip`` label. The ``documentation`` label is treated the same way. To run
a dry-run build matrix, use ``ci:dry-run``.

Releases
========

To cut a release, wait for the "MacOS Python build", "Linux Python build", and
"Windows Python build" GitHub Actions to complete successfully on the target commit.

Then, run the "Release" GitHub Action to create the release, populate the release artifacts (by
downloading the artifacts from each workflow, and uploading them to the GitHub Release), and promote
the SHA via the `latest-release` branch.

The "Release" GitHub Action takes, as input, a tag (assumed to be a date in `YYYYMMDD` format) and
the commit SHA referenced above.

For example, to create a release on April 19, 2024 at commit `29abc56`, run the "Release" workflow
with the tag `20240419` and the commit SHA `29abc56954fbf5ea812f7fbc3e42d87787d46825` as inputs,
once the "MacOS Python build", "Linux Python build", and "Windows Python build" workflows have
run to completion on `29abc56`.

When the "Release" workflow is complete, populate the release notes in the GitHub UI and promote
the pre-release to a full release, again in the GitHub UI.

At any stage, you can run the "Release" workflow in dry-run mode to avoid uploading artifacts to
GitHub. Dry-run mode can be executed before or after creating the release itself.
