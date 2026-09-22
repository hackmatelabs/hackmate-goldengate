#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
echo "=== SEP device models in source ==="
grep -rn -i -e 'sep' hw/arm/apple_rtkit.c | head -n 10
grep -rn -e '"sep"' -e 'arm-io/sep' -e 'sepfw' hw/arm/darwin.c hw/arm/apple_dtree.c 2>/dev/null | head -n 15
echo "=== live QOM tree (does SEP exist?) ==="
echo info qtree | nc -U /tmp/gg_diag.sock -w 8 | grep -a -i -e sep -e rtkit -e dcp -e ans | head -n 20
