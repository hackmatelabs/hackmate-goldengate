#!/bin/bash
set -euo pipefail

FW_DIR="firmware"
SHELL_LAUNCHD_PLIST="launchdaemons/com.jprx.bash.plist"
BUILD_TC="./build_tc.py"
SYS_SDK="macosx"

ramdisk="${FW_DIR}/ramdisk.dmg"

if [[ "$(uname)" != "Darwin" ]]; then
    echo "This isn't a Mac, so we can't patch the ramdisk- stopping here"
    exit 1
fi

echo "Patching ${ramdisk}"

livemount="$(mktemp -d)"

if [[ -z "${livemount}" || ! -d "${livemount}" ]]; then
    echo "something's wrong with the livemount, stopping here"
    exit 1
fi

if ! hdiutil attach -owners off -mountpoint "${livemount}" "${ramdisk}"; then
    rmdir "${livemount}"
    echo "mount failed"
    exit 1
fi

echo "mounted ${ramdisk} on ${livemount}"
trap 'hdiutil detach "${livemount}"; rmdir "${livemount}"' EXIT

if [[ -d "${livemount}/System/Library/LaunchDaemons.old" ]]; then
    echo "already patched"
    exit 0
fi

mv "${livemount}/System/Library/LaunchDaemons" "${livemount}/System/Library/LaunchDaemons.old"
mkdir "${livemount}/System/Library/LaunchDaemons"
cp "${SHELL_LAUNCHD_PLIST}" "${livemount}/System/Library/LaunchDaemons"

# SYS_SDK is macosx for our target (Macmini9,1) — no iOS sysroot injection needed,
# matching get_files.sh's own case statement (macosx branch is a no-op).

echo "building trustcache..."
find "${livemount}" -type f -exec codesign -d -vvv {} \; 2>&1 | grep -i cdhash= | cut -d= -f2- > "${FW_DIR}/all_hashes"
"${BUILD_TC}" "${FW_DIR}/all_hashes" "${FW_DIR}/ramdisk.tc"
echo "done!"
