# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from importlib.resources import files

# Several files in downloads.json are mirrored from their upstream sources due to
# flaky downloads (either intentional rate limiting or general low-availability /
# non-CDN infrastructure) and to reduce load on them. To
# update a file, push the new artifact to github.com/astral-sh/mirror (without
# removing the old artifact) and then update downloads.json once GitHub Pages has
# deployed. Feel free to point directly to the upstream source while working on
# a PR, especially if you don't have push access to astral-sh/mirror or are
# unsure if the PR will land, but we should make sure to switch back to the
# mirror shortly after landing the dependency.

with files("pythonbuild").joinpath("downloads.json").open("rb") as fh:
    DOWNLOADS = json.load(fh)
