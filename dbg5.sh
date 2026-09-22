#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
echo "=== helper.c ACNTVCT entry ==="
sed -n '2225,2245p' target/arm/helper.c
echo "=== sysreg/mrs handling in darwin machine ==="
grep -n 'MRS\|mrs\|SYSREG\|sysreg\|cp15\|CP15' hw/arm/darwin.c | head -n 20
echo "=== contagion: search xnuboot for counter/timer ==="
grep -n 'cntvct\|CNTVCT\|counter' hw/arm/xnuboot_sptm.c | head -n 20
