#!/bin/zsh
ls -la /Users/raahimsyed/goldengate/installer_work_26A428/26A428__MacOS/Firmware/ 2>/dev/null | head -n 30
echo "--- slide of current boot ---"
grep -a -e slide /tmp/gg_diag_stdout.log
