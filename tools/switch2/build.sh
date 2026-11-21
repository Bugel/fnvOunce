#!/bin/sh
# Runs a command (default: make) in a directory of this repository, inside the Switch 2 toolchain container
# (tools/switch2/Containerfile, image fnv-ounce). The repository is mounted at /src; files the build writes keep the
# caller's ownership (podman's rootless user namespace).
#   tools/switch2/build.sh port/switch2/probe            # make
#   tools/switch2/build.sh port/switch2/probe make clean
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
dir=${1:-.}
shift || true
[ $# -gt 0 ] || set -- make -j"$(nproc)"
exec podman run --rm -v "$root:/src" -w "/src/$dir" -e DEVKITPRO=/opt/devkitpro fnv-ounce \
    sh -c '. /opt/devkitpro/switch2vars.sh >/dev/null 2>&1; export PATH=/opt/devkitpro/tools/bin:$PATH; exec "$@"' sh "$@"
