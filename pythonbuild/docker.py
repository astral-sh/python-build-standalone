# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import contextlib
import io
import operator
import os
import pathlib
import tarfile

import docker  # type: ignore
import jinja2

from .logging import log, log_raw
from .utils import write_if_different


def write_dockerfiles(source_dir: pathlib.Path, dest_dir: pathlib.Path):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(source_dir)))

    for f in os.listdir(source_dir):
        if not f.endswith(".Dockerfile"):
            continue

        tmpl = env.get_template(f)
        data = tmpl.render()

        write_if_different(dest_dir / f, data.encode("utf-8"))


def build_docker_image(
    client, image_data: bytes, image_dir: pathlib.Path, name, host_platform
):
    image_path = image_dir / f"image-{name}.{host_platform}"

    return ensure_docker_image(client, io.BytesIO(image_data), image_path=image_path)


def ensure_docker_image(client, fh, image_path=None):
    res = client.api.build(fileobj=fh, decode=True)

    image = None

    for s in res:
        if "stream" in s:
            for l in s["stream"].strip().splitlines():
                log(l)

        if "aux" in s and "ID" in s["aux"]:
            image = s["aux"]["ID"]

        if "error" in s:
            log(s["error"])

    if not image:
        raise Exception("unable to determine built Docker image")

    if image_path:
        tar_path = pathlib.Path(str(image_path) + ".tar")
        with tar_path.open("wb") as fh:
            for chunk in client.images.get(image).save():
                fh.write(chunk)

        with image_path.open("w") as fh:
            fh.write(image + "\n")

    return image


def get_image(
    client, source_dir: pathlib.Path, image_dir: pathlib.Path, name, host_platform
):
    if client is None:
        return None

    image_name = f"image-{name}.{host_platform}"
    image_path = image_dir / image_name
    tar_path = image_path.with_suffix(".tar")

    with image_path.open("r") as fh:
        image_id = fh.read().strip()

    try:
        client.images.get(image_id)
        return image_id
    except docker.errors.ImageNotFound:
        if tar_path.exists():
            with tar_path.open("rb") as fh:
                data = fh.read()
            client.images.load(data)

            return image_id

        else:
            return build_docker_image(
                client, str(source_dir).encode(), image_dir, name, host_platform
            )


def copy_file_to_container(path, container, container_path, archive_path=None):
    """Copy a path on the local filesystem to a running container."""
    buf = io.BytesIO()
    tf = tarfile.open("irrelevant", "w", buf)

    dest_path = archive_path or path.name
    tf.add(str(path), dest_path)
    tf.close()

    log("copying %s to container:%s/%s" % (path, container_path, dest_path))
    container.put_archive(container_path, buf.getvalue())


@contextlib.contextmanager
def run_container(client, image):
    container = client.containers.run(
        image, command=["/bin/sleep", "86400"], detach=True
    )
    try:
        yield container
    finally:
        container.stop(timeout=0)
        container.remove()


def container_exec(container, command, user="build", environment=None):
    # docker-py's exec_run() won't return the exit code. So we reinvent the
    # wheel.
    create_res = container.client.api.exec_create(
        container.id, command, user=user, environment=environment
    )

    exec_output = container.client.api.exec_start(create_res["Id"], stream=True)

    for chunk in exec_output:
        for l in chunk.strip().splitlines():
            log(l)

        log_raw(chunk)

    inspect_res = container.client.api.exec_inspect(create_res["Id"])

    if inspect_res["ExitCode"] != 0:
        if "PYBUILD_BREAK_ON_FAILURE" in os.environ:
            print("to enter container: docker exec -it %s /bin/bash" % container.id)
            import pdb

            pdb.set_trace()

        raise Exception("exit code %d from %s" % (inspect_res["ExitCode"], command))


# 2019-01-01T00:00:00
DEFAULT_MTIME = 1546329600


def container_get_archive(container, path):
    """Get a deterministic tar archive from a container."""
    data, stat = container.get_archive(path)
    old_data = io.BytesIO()
    for chunk in data:
        old_data.write(chunk)

    old_data.seek(0)

    new_data = io.BytesIO()

    with (
        tarfile.open(fileobj=old_data) as itf,
        tarfile.open(fileobj=new_data, mode="w") as otf,
    ):
        for member in sorted(itf.getmembers(), key=operator.attrgetter("name")):
            file_data = itf.extractfile(member) if not member.linkname else None
            member.mtime = DEFAULT_MTIME
            otf.addfile(member, file_data)

    return new_data.getvalue()
