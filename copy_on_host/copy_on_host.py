"""
Python CLI script to copy a file on a Docker host from within a container.
"""
from __future__ import print_function
import argparse
import json
import logging
import logging.config
import os.path

from docker.client import Client
from docker.utils import kwargs_from_env


LOG = logging.getLogger(__name__)


def configure_logging():
    """Configures logging handlers for running as a script. Prints INFO and above to console by default."""
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s]: %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False,
            },
            '__main__': {
                'handlers': ['default'],
                'level': 'INFO',
                'propagate': False,
            },
        }
    })


def copy_file_via_docker(client, image_name, src_path, dest_path):
    """
    Copies a file from one location on the Docker host to another location on the Docker host, but from
    within a Docker container. This function will block/wait until the command is finished and then return
    the exit code and any output to stdout and stderr. Returns a 3-tuple of (exit code, stdout, stderr).

    :param client: docker.client.Client instance
    :param image_name: string name of the docker image to use
    :param src_path: string, a full path to a file on the docker host to copy
    :param dest_path: string, a full path to the destination on the docker host to copy `src_path` to
    :return: 3-tuple, (command exit code, command stdout, command stderr)
    """
    # Use the Docker client to pull a given image name. Downloading images can take a long time depending on the
    # size of the image and the user's network bandwidth. Download progress can be seen in verbose mode
    LOG.info("pulling docker image '%s'", image_name)
    for line in client.pull(image_name, stream=True):
        data = json.loads(line)
        if data['status'].lower() == 'downloading':
            LOG.debug("%s: %s", data['id'], data['progress'])
        elif 'id' in data:
            LOG.debug("%s: %s", data['id'], data['status'])
        else:
            LOG.debug("%s", data['status'])

    # Choose what path to mount from the host filesystem and where to mount it within the container. Mounting / is not
    # the best idea but for the sake of this demo script, we're going to do it so that any path given can be copied if
    # it is valid on the host
    host_path = '/'
    mount_point = '/mnt/host'
    LOG.debug("host filesystem '%s' will be mounted at '%s'", host_path, mount_point)

    # Setup the paths that will be given as arguments to the copy command by prepending the chosen mount point to
    # the `src_path` and `dest_path` arguments to make them valid within the container (assuming that the original
    # given paths are valid on the host).
    # Strip off any leading slash on `src_path` and `dest_path` because os.path.join() will lose the mount_point prefix
    # if the second part starts with a slash.
    src_path = os.path.join(mount_point, src_path.lstrip("/"))
    LOG.debug("src path: '%s'", src_path)
    dest_path = os.path.join(mount_point, dest_path.lstrip("/"))
    LOG.debug("dest path: '%s'", dest_path)

    # set up the `cp` command using the paths under the mount-point
    cmd = ["cp", "-v", src_path, dest_path]
    LOG.debug("command = '%s'", " ".join(cmd))

    LOG.debug("creating container")
    container = client.create_container(image=image_name, command=cmd, volumes=[mount_point])

    # start the container and bind the host's filesystem to the mount point
    LOG.info("starting container id=%s", container['Id'])
    client.start(container=container, binds={host_path: {'bind': mount_point, 'ro': False}})

    # wait until the command is complete and get its exit code
    LOG.debug("waiting until command is complete")
    exit_code = client.wait(container)
    LOG.log(logging.WARNING if exit_code > 0 else logging.DEBUG, "exit code was %i", exit_code)

    # get the stdout and stderr of the command. it does seem that we can get stdout and stderr separately,
    # but that has the downside that we would lose the output order. The next line could be used instead to
    # get stdout and stderr interleaved together and maintain output order.
    # output = client.logs(container, stdout=True, stderr=True)
    LOG.debug("getting stdout")
    stdout = client.logs(container, stdout=True, stderr=False).strip()
    LOG.debug("getting stderr")
    stderr = client.logs(container, stdout=False, stderr=True).strip()

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


def main():
    """
    Copies a file using a Docker container and prints the exit code and any output (stdout and/or stderr) produced
    by that command.

    :return: None
    """
    def full_path(path):
        """Converts path arguments to full absolute paths, expanding user shortcuts if given."""
        return os.path.abspath(os.path.expanduser(path))

    parser = argparse.ArgumentParser(description='Copy a file from within a docker container')
    parser.add_argument('src_path', help='The path of the file on the host to copy.', type=full_path)
    parser.add_argument('dest_path', help='The path on the host to copy the file to.', type=full_path)
    parser.add_argument('--image', default='ubuntu:14.04', help='Docker image to use')
    parser.add_argument('--verbose', action='store_true', help='Increase logging level (from INFO to DEBUG)')
    args = parser.parse_args()

    if args.verbose:
        LOG.setLevel(logging.DEBUG)

    exit_code, stdout, stderr = copy_file_via_docker(client=setup_client(), image_name=args.image,
                                                     src_path=args.src_path, dest_path=args.dest_path)

    print("-" * 30)
    print("Exit Code: {code}".format(code=exit_code))
    if stdout:
        print("Stdout:\n{out}".format(out=stdout))
    if stderr:
        print("Stderr:\n{err}".format(err=stderr))
    if not stdout and not stderr:
        print("No output")

if __name__ == '__main__':
    configure_logging()
    main()
