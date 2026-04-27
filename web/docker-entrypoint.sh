#!/bin/sh
# Bind mount at /data often arrives root-owned; app runs as slgpuweb (10001). Fix
# when we start as root, then drop privileges. tini(1) is in Dockerfile
# ENTRYPOINT, not in this script — avoids "tini is not running as PID 1" warnings.
# On some Docker Desktop / NTFS bind mounts, chown may be ignored — use a named
# volume (see docker/docker-compose.web.yml) or a Linux-native path for /data.
#
# Docker socket is typically mode 660 root:docker. After setpriv|runuser as 10001
# the process must be in a group with the *same* GID as the mounted socket, or
# the docker SDK gets PermissionError(13) (see gpasswd in block below).
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R 10001:10001 /data
  if [ -n "${WEB_SLGPU_ROOT:-}" ]; then
    # bench results: native.bench.* mkdir() as uid 10001 — must not be root-only (e.g. host ran ./slgpu bench)
    # data/web/secrets: generated langfuse-litellm.env for monitoring compose (not root-only configs/secrets)
    mkdir -p "${WEB_SLGPU_ROOT}/data/models" "${WEB_SLGPU_ROOT}/data/presets" \
      "${WEB_SLGPU_ROOT}/data/bench/results" \
      "${WEB_SLGPU_ROOT}/data/web/secrets" \
      "${WEB_SLGPU_ROOT}/data/web/.slgpu"
    chown -R 10001:10001 "${WEB_SLGPU_ROOT}/data/models" "${WEB_SLGPU_ROOT}/data/presets" \
      "${WEB_SLGPU_ROOT}/data/bench" "${WEB_SLGPU_ROOT}/data/web" 2>/dev/null || true
  fi
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
  exec runuser -u slgpuweb -- "$@"
fi
exec "$@"
