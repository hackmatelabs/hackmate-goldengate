#!/bin/bash
set -euo pipefail
FW_DIR="${1:?usage: fix_launchdaemons_owner.sh firmware_dir}"
ramdisk="${FW_DIR}/ramdisk.dmg"

livemount="$(mktemp -d)"
if ! hdiutil attach -owners off -mountpoint "${livemount}" "${ramdisk}"; then
    rmdir "${livemount}"
    echo "mount failed"
    exit 1
fi
trap 'hdiutil detach "${livemount}"; rmdir "${livemount}"' EXIT

echo "Before:"
ls -la "${livemount}/System/Library/LaunchDaemons/"

sudo chown -R root:wheel "${livemount}/System/Library/LaunchDaemons"

echo "After:"
ls -la "${livemount}/System/Library/LaunchDaemons/"
echo "done!"
