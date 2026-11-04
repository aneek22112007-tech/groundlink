#!/bin/sh
# The data volume is root-owned when Docker creates it. Claim it, then drop
# to the groundlink user. Preserve the environment compose injected.
set -eu
mkdir -p /data/switch-state
chown -R groundlink:groundlink /data
exec runuser --preserve-environment --user groundlink -- "$@"
