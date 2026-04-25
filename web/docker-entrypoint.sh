#!/bin/sh
# Bind mount at /data often arrives root-owned; app runs as slgpuweb (10001). Fix
# when we start as root, then drop privileges (tini + uvicorn in CMD).
# On some Docker Desktop / NTFS bind mounts, chown may be ignored — use a named
# volume (see web/docker-compose.yml) or a Linux-native path for /data.
#
# Docker socket is typically mode 660 root:docker. After setpriv|runuser as 10001
# the process must be in a group with the *same* GID as the mounted socket, or
# the docker SDK gets PermissionError(13) (see gpasswd in block below).
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R 10001:10001 /data
  if [ -S /var/run/docker.sock ]; then
    GID=$(stat -c %g /var/run/docker.sock)
    if [ -n "$GID" ] && [ "$GID" != "0" ]; then
      if ! getent group "$GID" >/dev/null; then
        groupadd -g "$GID" hostdocker
      fi
      GNAME=$(getent group "$GID" | cut -d: -f1)
      usermod -aG "$GNAME" slgpuweb 2>/dev/null || true
    fi
  fi
  exec runuser -u slgpuweb -- /usr/bin/tini -g -- "$@"
fi
exec /usr/bin/tini -g -- "$@"
