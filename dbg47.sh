#!/bin/zsh
F=/Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware/sptm.asidfix4
echo "=== DOUBLE_NEST / shared_region / sptm_set_shared / expected_shared ==="
strings -a "$F" | grep -i -e DOUBLE_NEST -e shared_region -e expected_shared -e DOUBLE | head -n 20
echo "=== sptm.c references ==="
strings -a "$F" | grep -e 'sptm\.c' | head -n 10
echo "=== NEST (any) ==="
strings -a "$F" | grep -e NEST | head -n 20
