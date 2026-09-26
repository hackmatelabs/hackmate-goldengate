#!/bin/zsh
echo "=== decision matrix lines in serial ==="
grep -a -e 'TRM ENABLED' -e 'DISABLED BY' -e 'TRM disabled' -e 'TRM will start' /tmp/gg_diag_serial.log | head -n 10
echo "=== current boot-args in log ==="
grep -a -m2 -e 'boot-args' /tmp/gg_diag_serial.log | head -n 4
