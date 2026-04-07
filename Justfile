# Diff 2 releases using diffoscope.
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

# Run the mirror uploader integration test against a local moto S3 server.
test-mirror-integration:
  uv run python -m unittest tests/test_mirror_integration.py

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
    git push origin latest-release
  else
    echo "No changes to commit."
  fi

  git switch main

# Create a GitHub release object, or reuse an existing draft release.
release-create tag:
  #!/usr/bin/env bash
  set -euo pipefail
  draft_exists=$(gh release view {{tag}} --json isDraft -t '{{{{.isDraft}}' 2>&1 || true)
  case "$draft_exists" in
    true)
      echo "note: updating existing draft release {{tag}}"
      ;;
    false)
      echo "error: release {{tag}} already exists and is not a draft"
      exit 1
      ;;
    "release not found")
      gh release create {{tag}} --draft --title {{tag}} --notes TBD --verify-tag
      ;;
    *)
      echo "error: unexpected gh cli output: $draft_exists"
      exit 1
      ;;
  esac

# Publish the draft GitHub release and promote the tag to latest-release.
release-finalize tag:
  #!/usr/bin/env bash
  set -euo pipefail
  gh release edit {{tag}} --draft=false --latest
  just release-set-latest-release {{tag}}

# Upload release artifacts to an S3-compatible mirror bucket with the correct release names.
# AWS credentials are read from the standard AWS_* environment variables.
# Requires `release-run` to have been run so that dist/SHA256SUMS exists.
release-upload-mirror bucket prefix tag:
  uv run python -m pythonbuild.mirror \
    --dist dist \
    --tag {{tag}} \
    --bucket {{bucket}} \
    --prefix {{prefix}}

# Dry-run the mirror upload without writing to the bucket.
# Requires `release-run` or `release-dry-run` to have been run so that dist/SHA256SUMS exists.
release-upload-mirror-dry-run bucket prefix tag:
  uv run python -m pythonbuild.mirror \
    --dist dist \
    --tag {{tag}} \
    --bucket {{bucket}} \
    --prefix {{prefix}} \
    -n

# Perform the release job. Assumes that the GitHub Release has been created.
release-run token commit tag:
  #!/bin/bash
  set -eo pipefail

  rm -rf dist
  just release-download-distributions {{token}} {{commit}}
  datetime=$(ls dist/cpython-3.10.*-x86_64-unknown-linux-gnu-install_only-*.tar.gz  | awk -F- '{print $8}' | awk -F. '{print $1}')
  just release-upload-distributions {{token}} ${datetime} {{tag}}
  just release-finalize {{tag}}

# Perform a release in dry-run mode.
release-dry-run token commit tag:
  #!/bin/bash
  set -eo pipefail

  rm -rf dist
  just release-download-distributions {{token}} {{commit}}
  datetime=$(ls dist/cpython-3.10.*-x86_64-unknown-linux-gnu-install_only-*.tar.gz  | awk -F- '{print $8}' | awk -F. '{print $1}')
  just release-upload-distributions-dry-run {{token}} ${datetime} {{tag}}
