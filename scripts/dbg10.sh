#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
F=firmware/dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid
echo "--- dtree size ---"
ls -la "$F"
echo "--- cpu node count (name cpu@) ---"
grep -a -o -e 'cpu@[0-9a-f]*' "$F" | sort -u
echo "--- device_type=cpu count ---"
grep -a -c 'device_type' "$F"
echo "--- ncpu-ish props ---"
strings -a "$F" | grep -i -e '^ncpu' -e 'num-cpus' -e 'cpu-count' | head
echo "--- compatible of cpus ---"
grep -a -o -e 'arm,armv8' "$F" | wc -l
echo "--- QEMU smp default check: machine darwin cpus ---"
grep -n 'max_cpus\|min_cpus\|default_cpu' hw/arm/darwin.c | head
