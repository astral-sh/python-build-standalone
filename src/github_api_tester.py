#!/usr/bin/env -S uv run
#
# A fake GitHub API server for testing upload-release-distributions's
# behavior in the presence of API failures.
#
# Call with no arguments or with pytest CLI arguments to run the tests
# at the bottom which invoke `cargo run`.
#
# Call with one argument "serve" to start an HTTP server on 0.0.0.0.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "quart>=0.20.0",
#     "quart-trio>=0.12.0",
#     # Pinned because we mess with hypercorn internals, see below.
#     "hypercorn==0.17.3",
#     "pytest",
#     "pytest-trio",
# ]
# ///

import dataclasses
import hashlib
import logging
import os
import sys
from collections.abc import Callable

import hypercorn
import pytest
import quart
import trio
from quart import request
from quart_trio import QuartTrio

app = QuartTrio(__name__)
app.config["MAX_CONTENT_LENGTH"] = None


async def drop_connection():
    """Drop the (HTTP/1.1) connection belonging to the current Quart request."""
    # We need to do two things:
    # - Convince hypercorn (specifically, around HTTPStream.app_send())
    #   that it doesn't need to send a 500 and can just close the socket.
    # - Convince h11's state machine that it's okay to close the socket
    #   without sending a response.
    # We can't do this at the ASGI layer: hypercorn will insert the 500
    # for protocol compliance if the ASGI app doesn't provide a
    # response. We need to modify the actual HTTP server, either with a
    # pull request or by digging into its internals as follows:
    # - Grab the HTTPStream whose bound method app_send was passed into
    #   the Quart request
    # - Grab the H11Protocol whose bound method stream_send was passed
    #   into the HTTPStream's constructor
    # - Tell the H11Protocol's underlying h11 state machine to act as if
    #   the remote side errored, so it thinks dropping the connection is
    #   the appropriate next step and not misbehavior on our end
    # - Tell the HTTPStream to move the state machine forward with no
    #   further send on our side, which will drop the connection (and
    #   not consider it for keepalive)
    import hypercorn.protocol as hp

    http_stream: hp.http_stream.HTTPStream = request._send_push_promise.args[0].__self__
    protocol: hp.h11.H11Protocol = http_stream.send.__self__
    protocol.connection._process_error(protocol.connection.their_role)
    await http_stream.send(hp.events.EndBody(stream_id=http_stream.stream_id))
    await http_stream.app_send(None)

    # Some other things I tried, kept for reference:
    # http_stream.state = hypercorn.protocol.http_stream.ASGIHTTPState.RESPONSE
    # await http_stream._send_closed()
    # http_stream.state = hypercorn.protocol.http_stream.ASGIHTTPState.CLOSED


# The following GitHub API datatypes are complete enough to satisfy
# octocrab's deserialization.


@dataclasses.dataclass
class Asset:
    name: str
    label: str | None
    sha256: str
    contents: bytes | None

    _ASSETS = []

    def __post_init__(self):
        self.id = len(self._ASSETS)
        self._ASSETS.append(self)

    def render(self) -> dict:
        return {
            "url": quart.url_for("get_asset", id=self.id, _external=True),
            "browser_download_url": "https://github.invalid/unneeded",
            "id": self.id,
            "node_id": "fakenode",
            "name": self.name,
            "label": self.label,
            "state": "uploaded",
            "content_type": "application/octet-stream",
            "size": 1000,
            "download_count": 1000,
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2020-01-01T00:00:00Z",
            "uploader": None,
        }


@dataclasses.dataclass
class Upload:
    name: str
    label: str | None

    def __post_init__(self):
        self.hasher = hashlib.sha256()
        if self.name == "SHA256SUMS":
            self.contents = b""
        else:
            self.contents = None

    def update(self, chunk: bytes) -> None:
        self.hasher.update(chunk)
        if self.contents is not None:
            self.contents += chunk

    def to_asset(self) -> Asset:
        return Asset(self.name, self.label, self.hasher.hexdigest(), self.contents)


@dataclasses.dataclass
class Release:
    release_id: int
    tag_name: str
    assets: list = dataclasses.field(default_factory=list)
    # fault0 and fault1 are called before and after receiving the first
    # chunk of a PUT request, respectively. Each is called once per
    # release - the first upload that hits it will disarm it.
    fault0: Callable[[], None] | None = None
    fault1: Callable[[], None] | None = None

    def render(self) -> dict:
        upload_asset = quart.url_for(
            "upload_asset", release=self.release_id, _external=True
        )
        return {
            "url": request.url,
            "html_url": "https://github.invalid/unneeded",
            "assets_url": "https://github.invalid/unneeded",
            "upload_url": upload_asset + "{?name,label}",
            "id": self.release_id,
            "node_id": "fakenode",
            "tag_name": self.tag_name,
            "target_commitish": "main",
            "draft": False,
            "prerelease": True,
            "assets": [i.render() for i in self.assets],
        }


releases = [
    Release(1, "basic"),
    Release(11, "early-drop", fault0=drop_connection),
    Release(12, "late-drop", fault1=drop_connection),
    Release(4011, "early-401", fault0=lambda: quart.abort(401)),
    Release(4012, "late-401", fault1=lambda: quart.abort(401)),
    Release(4031, "early-403", fault0=lambda: quart.abort(403)),
    Release(4032, "late-403", fault1=lambda: quart.abort(403)),
    Release(5001, "early-500", fault0=lambda: quart.abort(500)),
    Release(5002, "late-500", fault1=lambda: quart.abort(500)),
]


def get_release(*, tag=None, release=None) -> Release:
    if tag is not None:
        condition = lambda r: r.tag_name == tag
    elif release is not None:
        condition = lambda r: r.release_id == release
    else:
        raise TypeError("tag or release must be set")

    for r in releases:
        if condition(r):
            return r
    quart.abort(404, response=quart.jsonify({"message": "Not Found", "status": "404"}))


# GitHub API functions


@app.route("/repos/<org>/<repo>/releases/tags/<tag>")
async def get_release_by_tag(org, repo, tag):
    return get_release(tag=tag).render()


@app.route("/repos/<org>/<repo>/releases/<int:release>")
async def get_release_by_id(org, repo, release):
    return get_release(release=release).render()


@app.put("/upload/<int:release>/assets")
async def upload_asset(release):
    filename = request.args["name"]
    release = get_release(release=release)

    if (fault := release.fault0) is not None:
        logging.info(f"{filename}: injecting fault0")
        release.fault0 = None
        return await fault()

    logging.info(f"{filename}: upload begin")
    upload = Upload(filename, request.args.get("label"))
    async for chunk in request.body:
        logging.debug(f"{filename}: {len(chunk)=}")
        upload.update(chunk)
        if (fault := release.fault1) is not None:
            if "SHA256" not in filename:
                logging.info(f"{filename}: injecting fault1")
                release.fault1 = None
                return await fault()

    asset = upload.to_asset()
    logging.info(f"{filename}: upload complete, {asset.sha256=}")
    release.assets.append(asset)
    return asset.render()


@app.route("/get_asset/<int:id>")
@app.route("/repos/<org>/<repo>/releases/assets/<int:id>")
async def get_asset(id, org=None, repo=None):
    try:
        asset = Asset._ASSETS[id]
    except IndexError:
        quart.abort(
            404, response=quart.jsonify({"message": "Not Found", "status": "404"})
        )

    if "application/octet-stream" in request.accept_mimetypes:
        if asset.contents is None:
            print(
                f"USAGE ERROR: Received request for contents of {asset.filename=} which was not stored"
            )
            return "Did not store contents", 410
        return asset.contents
    else:
        return asset.render()


# Generic upload function, useful for testing clients in isolation


@app.put("/file/<path:path>")
async def upload_file(path):
    logging.info(f"{path}: upload begin")
    s = hashlib.sha256()
    async for chunk in request.body:
        logging.debug(f"{path}: {len(chunk)=}")
        if "drop" in request.args:
            await drop_connection()
        s.update(chunk)
    digest = s.hexdigest()
    logging.info(f"{path}: {digest=}")
    return f"{digest}  {path}\n", 500


# Test cases


@pytest.fixture
async def server(nursery):
    await nursery.start(app.run_task)


FILENAME = "cpython-3.0.0-x86_64-unknown-linux-gnu-install_only-19700101T1234.tar.gz"
SHA256_20MEG = "9e21c61969cd3e077a1b2b58ddb583b175e13c6479d2d83912eaddc23c0cdd52"


@pytest.fixture(scope="session")
def upload_release_distributions(tmp_path_factory):
    dist = tmp_path_factory.mktemp("dist")
    filename = dist / FILENAME
    filename.touch()
    os.truncate(filename, 20_000_000)

    async def upload_release_distributions(*args):
        return await trio.run_process(
            [
                "cargo",
                "run",
                "--",
                "upload-release-distributions",
                "--github-uri",
                "http://localhost:5000",
                "--token",
                "no-token-needed",
                "--dist",
                dist,
                "--datetime",
                "19700101T1234",
                "--ignore-missing",
            ]
            + list(args)
        )

    return upload_release_distributions


# TODO: test all of [r.tag_name for r in releases]
TAGS_TO_TEST = ["basic", "early-drop", "late-drop", "early-403", "late-403"]


@pytest.mark.parametrize("tag", TAGS_TO_TEST)
async def test_upload(server, upload_release_distributions, tag):
    with trio.fail_after(300):
        await upload_release_distributions("--tag", tag)
    release = get_release(tag=tag)
    assets = sorted(release.assets, key=lambda a: a.name)
    assert len(assets) == 2
    assert assets[0].name == "SHA256SUMS"
    filename = FILENAME.replace("3.0.0", f"3.0.0+{tag}").replace("-19700101T1234", "")
    assert assets[1].name == filename
    assert assets[1].sha256 == SHA256_20MEG
    assert assets[0].contents == f"{SHA256_20MEG}  {filename}\n".encode()


# Work around https://github.com/pgjones/hypercorn/issues/238 not being in a release
# Without it, test failures are unnecessarily noisy
hypercorn.trio.lifespan.LifespanFailureError = trio.Cancelled

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        logging.basicConfig(level=logging.INFO)
        app.run("0.0.0.0")
    else:
        pytest.main(["-o", "trio_mode=true", __file__] + sys.argv[1:])
