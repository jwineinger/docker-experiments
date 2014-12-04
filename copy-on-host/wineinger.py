from __future__ import print_function

import json
import os.path

from docker.client import Client
from docker.utils import kwargs_from_env


def copy_file_via_docker(client, image_name, src_path, dest_path):
    """
    Copies a file from one location on the Docker host to another location on the Docker host, but from
    within a Docker container. This function will block/wait until the command is finished and then return
    the exit code and any output to stdout and stderr.

    :param client: docker.client.Client instance
    :param image_name: string name of the docker image to use
    :param src_path: string, a full path to a file on the docker host to copy
    :param dest_path: string, a full path to the destination on the docker host to copy `src_path` to
    :return: 3-tuple, (command exit code, command stdout, command stderr)
    """
    # Use the Docker `client` to pull a given image name. The output of this command is printed in
    # a streaming fashion in order to give the user feedback as to what is going on. Downloading an image can
    # take a long time depending on the size of the image and the user's network bandwidth.
    for line in client.pull(image_name, stream=True):
        print(json.dumps(json.loads(line), indent=4))

    # Setup the paths that will be given to the copy command as the src and destination. To do that,
    # choose where to mount the host filesystem within the container. Then prepend that mount point to
    # the `src_path` and `dest_path` arguments so that they are valid within the container (assuming that the
    # original given paths are valid on the host).
    # Mounting / is not the best idea but for the sake of this demo script, we're going to do it so that any path
    # given can be copied if it is valid on the host
    host_path = '/'
    mount_point = '/mnt/host'

    # Strip off the leading char of src_path and dest_path because it will be a slash, and os.path.join() will lose
    # the mount_point prefix if the second part starts with a slash.
    src = os.path.join(mount_point, src_path[1:])
    dest = os.path.join(mount_point, dest_path[1:])

    # set up the `cp` command using the paths under the mount-point
    cmd = ["cp", src, dest]

    container = client.create_container(image=image_name, command=cmd, volumes=[mount_point])

    # start the container and bind the host's root to the mount point
    client.start(container=container, binds={host_path: {'bind': mount_point, 'ro': False}})

    # wait until the command is complete and get its exit code
    exit_code = client.wait(container)

    # get the stdout and stderr of the command. it does seem that we can get stdout and stderr separately,
    # but that has the downside that we would lose the output order. The next line could be used instead to
    # get stdout and stderr interleaved together and maintain output order.
    # output = client.logs(container, stdout=True, stderr=True)
    stderr = client.logs(container, stdout=False, stderr=True).strip()
    stdout = client.logs(container, stdout=True, stderr=False).strip()

    return exit_code, stdout, stderr


def setup_client():
    """
    Creates a Docker client instance. Currently this always uses the docker-specific environment vars
    to configure the client. See http://docker-py.readthedocs.org/en/latest/boot2docker/

    To fix a TLS error if using boot2docker, you may need to add a hosts file entry for the boot2docker IP address and
    then update your DOCKER_HOST environment variable as follows:
        export DOCKER_HOST=tcp://boot2docker:2376

    :return: docker.client.Client instance
    """
    return Client(**kwargs_from_env())


def main(**kwargs):
    """
    Copies a file using a Docker container and prints the exit code and any output (stdout and/or stderr) produced
    by that command.
    
    :return: None
    """
    exit_code, stdout, stderr = copy_file_via_docker(client=setup_client(), **kwargs)

    print("-" * 30)
    print("Exit Code: {code}".format(code=exit_code))
    if stdout:
        print("Stdout:\n{out}".format(out=stdout))
    if stderr:
        print("Stderr:\n{err}".format(err=stderr))


if __name__ == '__main__':
    import argparse

    def full_path(path):
        """Converts path arguments to full absolute paths, expanding user shortcuts if given"""
        return os.path.abspath(os.path.expanduser(path))

    parser = argparse.ArgumentParser(description='Copy a file from within a docker container')
    parser.add_argument('src_path', help='The path of the file on the host to copy.', type=full_path)
    parser.add_argument('dest_path', help='The path on the host to copy the file to.', type=full_path)
    parser.add_argument('-i', '--image', default='ubuntu:14.04', help='Docker image to use')
    args = parser.parse_args()

    main(image_name=args.image, src_path=args.src_path, dest_path=args.dest_path)
