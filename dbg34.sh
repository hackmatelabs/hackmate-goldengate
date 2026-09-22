#!/bin/zsh
echo "=== sepfw hunt ==="
ls /Users/raahimsyed/goldengate/installer_work_26A428/img4_extracted/ 2>/dev/null
ls /Users/raahimsyed/goldengate/installer_work_26A428/26A428__MacOS/ 2>/dev/null
find /Users/raahimsyed/goldengate/installer_work_26A428 -maxdepth 3 -iname '*sep*' 2>/dev/null | head -n 10
find /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware -maxdepth 1 -iname '*sep*' 2>/dev/null | head
echo "=== relaunch clean ==="
pkill -f gg_diag.sock
sleep 2
/Users/raahimsyed/launch_netboot2.sh
sleep 20
ps aux | grep qemu-system | grep -v grep | wc -l
