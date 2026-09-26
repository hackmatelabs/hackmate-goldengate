#!/bin/zsh
echo "=== TRM lines in live serial log ==="
grep -a -e 'TRM' /tmp/gg_diag_serial.log | head -n 20
echo "=== trm boot-arg/DT names in bootkc ==="
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
strings -a bootkc.md0size.uidfix.netboot1 | grep -i -e 'trm_enabled' -e 'trm-disable' -e 'trm_disable' -e 'disable.*trm' -e 'trm.*boot-arg' -e 'acm.*trm' | sort -u | head -n 20
echo "=== DT= source: device-tree trm props? ==="
strings -a bootkc.md0size.uidfix.netboot1 | grep -i -e 'trm' | grep -i -e 'chosen' -e 'device-tree' -e 'dt-' | head -n 10
