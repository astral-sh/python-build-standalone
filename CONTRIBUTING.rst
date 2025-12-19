============
Contributing
============

Building distributions
======================

See the [documentation](https://gregoryszorc.com/docs/python-build-standalone/main/building.html)
for instructions on building distributions locally.

CI labels
=========
By default, submitting a pull request triggers a complete build of all
distributions in CI, which can be time-consuming.

To conserve CI resources and reduce build times, you can limit the matrix of
distributions built by applying specific labels to your pull request. Only
distributions matching the specified labels will be built.

The following label prefixes can be used to customize the build matrix:

* `platform`
* `python`
* `build`
* `arch`
* `libc`

To bypass CI entirely for changes that do not affect the build (such as
documentation updates), use the `ci:skip` label.

Please utilize these tags when appropriate for your changes to minimize CI
resource consumption.

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
