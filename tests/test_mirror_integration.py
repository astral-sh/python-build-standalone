# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import boto3
from moto.server import ThreadedMotoServer

from pythonbuild.mirror import CACHE_CONTROL, main


class MirrorIntegrationTests(unittest.TestCase):
    def test_uploads_artifacts_to_mock_s3(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / "dist"
            dist.mkdir()

            full_path = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-pgo+lto-20260324T1200.tar.zst"
            )
            install_only_path = (
                dist
                / "cpython-3.12.10-x86_64-unknown-linux-gnu-install_only-20260324T1200.tar.gz"
            )
            shasums_path = dist / "SHA256SUMS"

            full_path.write_bytes(b"full")
            install_only_path.write_bytes(b"install")
            shasums_path.write_text(
                "abc  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst\n"
                "def  cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz\n"
            )

            server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
            server.start()
            try:
                host, port = server.get_host_and_port()
                endpoint_url = f"http://{host}:{port}"
                bucket = "mirror-bucket"
                prefix = "github/python-build-standalone/releases/download/20260324/"

                s3 = boto3.client(
                    "s3",
                    endpoint_url=endpoint_url,
                    region_name="us-east-1",
                    aws_access_key_id="testing",
                    aws_secret_access_key="testing",
                )
                s3.create_bucket(Bucket=bucket)

                with mock.patch.dict(
                    os.environ,
                    {
                        "AWS_ACCESS_KEY_ID": "testing",
                        "AWS_SECRET_ACCESS_KEY": "testing",
                        "AWS_DEFAULT_REGION": "us-east-1",
                        "AWS_ENDPOINT_URL": endpoint_url,
                    },
                ):
                    self.assertEqual(
                        main(
                            [
                                "--dist",
                                str(dist),
                                "--tag",
                                "20260324",
                                "--bucket",
                                bucket,
                                "--prefix",
                                prefix,
                            ]
                        ),
                        0,
                    )

                objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
                self.assertEqual(
                    sorted(obj["Key"] for obj in objects["Contents"]),
                    [
                        prefix + "SHA256SUMS",
                        prefix
                        + "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz",
                        prefix
                        + "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
                    ],
                )

                install_only_object = s3.get_object(
                    Bucket=bucket,
                    Key=prefix
                    + "cpython-3.12.10+20260324-x86_64-unknown-linux-gnu-install_only.tar.gz",
                )
                self.assertEqual(install_only_object["Body"].read(), b"install")
                self.assertEqual(install_only_object["CacheControl"], CACHE_CONTROL)

                shasums_object = s3.get_object(Bucket=bucket, Key=prefix + "SHA256SUMS")
                self.assertEqual(
                    shasums_object["Body"].read(), shasums_path.read_bytes()
                )
                self.assertEqual(shasums_object["CacheControl"], CACHE_CONTROL)
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
