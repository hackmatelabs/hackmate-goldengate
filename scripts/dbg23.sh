#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
F=bootkc.md0size.uidfix.netboot1
echo "=== BootPolicy string contexts (which kext publishes it?) ==="
grep -a -o -e '.\{80\}BootPolicy.\{120\}' "$F" | grep -a -v -e 'bootpolicy_' -e 'BootPolicy:' | head -n 15
echo "=== AppleSEPManager present? ==="
grep -a -c -e 'AppleSEPManager' "$F"
echo "=== RTBuddy kexts in bootkc ==="
grep -a -o -e 'com\.apple\.driver\.RTBuddy[A-Za-z]*' "$F" | sort -u | head
echo "=== AppleDCP in bootkc? ==="
grep -a -c -e 'com\.apple\.driver\.AppleDCP' "$F"
