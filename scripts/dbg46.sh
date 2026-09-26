#!/bin/zsh
F=/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4
ls -la "$F"
echo "=== VIOLATION / DOUBLE_NEST / shared_region strings ==="
strings -a "$F" | grep -i -e VIOLATION -e DOUBLE_NEST -e shared_region | head -n 30
