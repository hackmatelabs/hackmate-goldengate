#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
echo "=== patch sites in xnu_patch.c ==="
grep -n -e 'patch_' -e 'get_addr' -e 'find_' hw/arm/xnu_patch.c | head -n 40
echo "=== string anchors used ==="
grep -n -e '"[^"]*"' hw/arm/xnu_patch.c | head -n 40
