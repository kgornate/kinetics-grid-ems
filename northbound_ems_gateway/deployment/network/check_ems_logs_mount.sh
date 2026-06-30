#!/bin/sh
set -eu
MOUNT_PATH="${1:-/mnt/ems-logs}"
echo "Checking EMS logs mount: ${MOUNT_PATH}"
if findmnt "${MOUNT_PATH}" >/dev/null 2>&1; then
  df -h "${MOUNT_PATH}"
  echo "OK: mounted"
else
  echo "ERROR: ${MOUNT_PATH} is not mounted" >&2
  exit 1
fi
