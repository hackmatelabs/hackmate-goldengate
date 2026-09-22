#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
ls -la sptm* txm*
echo "=== asidfix3 vs asidfix4 ==="
cmp -l sptm.asidfix3 sptm.asidfix4 2>/dev/null | head -n 20
echo "=== sizes ==="
md5 sptm.asidfix3 sptm.asidfix4 2>/dev/null
