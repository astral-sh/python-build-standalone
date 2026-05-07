#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

mkdir -p out/tools/deps/share/certifi
unzip -p "certifi-${CERTIFI_VERSION}-py3-none-any.whl" certifi/cacert.pem \
  > out/tools/deps/share/certifi/cacert.pem
