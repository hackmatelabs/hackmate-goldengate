#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
echo "--- ACNTVCT refs in helper.c ---"
grep -n 'ACNTVCT' target/arm/helper.c | head -20
echo "--- c15_c10 refs ---"
grep -rn 'c15_c10' target/arm/helper.c | head -20
echo "--- gt_get_countervalue refs ---"
grep -rn 'gt_get_countervalue' target/arm/ | head -10
echo "--- QEMU pid ---"
pgrep -f gg_diag.sock
