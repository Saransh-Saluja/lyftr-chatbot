#!/bin/sh
# Start as root ONLY long enough to make the data directory writable, then drop
# to the unprivileged user (uid 10001) before the app starts.
#
# Why: a named volume (docker compose) inherits /data's ownership from the image,
# but a platform-mounted disk (e.g. Render) usually arrives owned by root, which
# would make SQLite fail with "unable to open database file".
set -e
DATA_DIR="${DATA_DIR:-/data}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  chown 10001:10001 "$DATA_DIR" || echo "warning: could not chown $DATA_DIR" >&2
  # Drop privileges using Python (always present in this image; no extra packages).
  exec python -c 'import os, sys; os.setgroups([]); os.setgid(10001); os.setuid(10001); os.execvp(sys.argv[1], sys.argv[1:])' "$@"
fi
exec "$@"
