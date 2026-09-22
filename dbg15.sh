#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
F=dtree.dcp8.bigdram2.dcpbyte.nubx.bsroot.nopda.bootuuid
echo "--- node names containing cpu ---"
grep -a -o -e '[A-Za-z0-9_,-]*[Cc][Pp][Uu][A-Za-z0-9_,-]*' "$F" | sort | uniq -c | sort -rn | head -n 25
echo "--- cpus node? ---"
grep -a -c -e 'cpus' "$F"
echo "--- cluster? ---"
grep -a -o -e '[A-Za-z0-9_,-]*cluster[A-Za-z0-9_,-]*' "$F" | sort -u | head
