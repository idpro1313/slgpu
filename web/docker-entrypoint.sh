#!/bin/sh
# Bind mount at /data often arrives root-owned; app runs as slgpuweb (10001). Fix
# when we start as root, then drop privileges (tini + uvicorn in CMD).
# On some Docker Desktop / NTFS bind mounts, chown may be ignored — use a named
# volume (see web/docker-compose.yml) or a Linux-native path for /data.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R 10001:10001 /data
  exec setpriv --reuid=10001 --regid=10001 --init-groups -- \
    /usr/bin/tini -g -- "$@"
fi
exec /usr/bin/tini -g -- "$@"
