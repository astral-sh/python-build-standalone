# Diff 2 releases using diffocope.
diff a b:
  diffoscope \
    --html build/diff.html \
    --exclude 'python/build/**' \
    --exclude-command '^readelf.*' \
    --exclude-command '^xxd.*' \
    --exclude-command '^objdump.*' \
    --exclude-command '^strings.*' \
    --max-report-size 9999999999 \
    --max-page-size 999999999 \
    --max-diff-block-lines 100000 \
    --max-page-diff-block-lines 100000 \
    {{ a }} {{ b }}

diff-python-json a b:
  diffoscope \
    --html build/diff.html \
    --exclude 'python/build/**' \
    --exclude 'python/install/**' \
    --max-diff-block-lines 100000 \
    --max-page-diff-block-lines 100000 \
    {{ a }} {{ b }}

cat-python-json archive:
  tar -x --to-stdout -f {{ archive }} python/PYTHON.json

# Download release artifacts from GitHub Actions
release-download-distributions token commit:
  mkdir -p dist
  cargo run --release -- fetch-release-distributions --token {{token}} --commit {{commit}} --dest dist

# Upload release artifacts to a GitHub release.
release-upload-distributions token datetime tag:
  cargo run --release -- upload-release-distributions --token {{token}} --datetime {{datetime}} --tag {{tag}} --dist dist

# "Upload" release artifacts to a GitHub release in dry-run mode (skip upload).
release-upload-distributions-dry-run token datetime tag:
  cargo run --release -- upload-release-distributions --token {{token}} --datetime {{datetime}} --tag {{tag}} --dist dist -n

# Promote a tag to "latest" by pushing to the `latest-release` branch.
release-set-latest-release tag:
  #!/usr/bin/env bash
  set -euxo pipefail

  git fetch origin
  git switch latest-release
  git reset --hard origin/latest-release

  cat << EOF > latest-release.json
  {
    "version": 1,
    "tag": "{{tag}}",
    "release_url": "https://github.com/astral-sh/python-build-standalone/releases/tag/{{tag}}",
    "asset_url_prefix": "https://github.com/astral-sh/python-build-standalone/releases/download/{{tag}}"
  }
  EOF

  # If the branch is dirty, we add and commit.
  if ! git diff --quiet; then
    git add latest-release.json
    git commit -m 'set latest release to {{tag}}'
    git switch main

    git push origin latest-release
  else
    echo "No changes to commit."
  fi

# Perform the release job. Assumes that the GitHub Release has been created.
release-run token commit tag:
  #!/bin/bash
  set -eo pipefail

  rm -rf dist
  just release-download-distributions {{token}} {{commit}}
  datetime=$(ls dist/cpython-3.10.*-x86_64-unknown-linux-gnu-install_only-*.tar.gz  | awk -F- '{print $8}' | awk -F. '{print $1}')
  just release-upload-distributions {{token}} ${datetime} {{tag}}
  just release-set-latest-release {{tag}}

# Perform a release in dry-run mode.
release-dry-run token commit tag:
  #!/bin/bash
  set -eo pipefail

  rm -rf dist
  just release-download-distributions {{token}} {{commit}}
  datetime=$(ls dist/cpython-3.10.*-x86_64-unknown-linux-gnu-install_only-*.tar.gz  | awk -F- '{print $8}' | awk -F. '{print $1}')
  just release-upload-distributions-dry-run {{token}} ${datetime} {{tag}}

_download-stats mode:
    build/venv.*/bin/python3 -c 'import pythonbuild.utils as u; u.release_download_statistics(mode="{{mode}}")'

# Show download counts of every release asset.
download-stats:
    just _download-stats by_asset

# Show download counts of release assets by build configuration.
download-stats-by-build:
    just _download-stats by_build

# Show download counts of "install only" release assets by build configuration.
download-stats-by-build-install-only:
    just _download-stats by_build_install_only

# Show download counts of release assets by release tag.
download-stats-by-tag:
    just _download-stats by_tag

# Show a total count of all release asset downloads.
download-stats-total:
    just _download-stats total
