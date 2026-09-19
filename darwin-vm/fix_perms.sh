#!/bin/bash
set -euo pipefail

fixup_perms() {
    local ramdisk="${1}"
    livemount="$(mktemp -d)"

    if [[ -z "${livemount}" || ! -d "${livemount}" ]]; then
        echo "something's wrong with the livemount, stopping here"
        exit 1
    fi

    if ! hdiutil attach -owners on -mountpoint "${livemount}" "${ramdisk}"; then
        echo "mount failed"
        rmdir "${livemount}"
        exit 1
    fi

    echo "mounted ${ramdisk} on ${livemount}"
    trap 'hdiutil detach ${livemount}; rmdir ${livemount}' EXIT

    echo "This will run: sudo chown -R root:wheel ${livemount}/bin ${livemount}/System ${livemount}/libexec"
    read -r -p "Are you sure? (y/n) " response
    echo "${response}"

    case "${response}" in
        [Yy])
            sudo chown -R root:wheel "${livemount}/bin" "${livemount}/System"

            if [[ -d "${livemount}/libexec" ]]; then
                sudo chown -R root:wheel "${livemount}/libexec"
            fi
            echo "done!"
            ;;
        *)
            echo "skipping permission fixes"
            ;;
    esac
}

main() {
    if [[ -z "${1:-}" ]]; then
        echo "usage: fix_perms.sh [ramdisk.dmg]"
        exit 1
    fi

    if [[ "$(uname)" != "Darwin" ]]; then
        echo "you need to run this on a Mac"
        exit 1
    fi

    fixup_perms "${1}"
}

main "$@"
