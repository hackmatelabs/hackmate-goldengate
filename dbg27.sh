#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
F=dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid
echo "=== cluster-power-down? ==="
grep -a -c -e 'cluster-power-down' "$F"
echo "=== cpus node children ==="
grep -a -o -e 'cpu[0-9][a-z0-9_@-]*' "$F" | sort -u | head -n 15
echo "=== cluster-type values ==="
grep -a -o -e 'cluster-type' "$F" | wc -l
echo "=== hang PC ==="
echo info registers | nc -U /tmp/gg_diag.sock -w 3 | grep -a PC=
