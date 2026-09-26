#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
F=bootkc.md0size.uidfix.netboot1
echo "--- TRM/BS daemon strings ---"
strings -a "$F" | grep -i -e 'BS daemon' -e 'TRM will start' -e 'BaseSystemBooted' -e 'TRM enabled' | head -n 20
echo "--- ACM TRM strings ---"
strings -a "$F" | grep -e '_onBaseSystemBooted' -e 'ACMTRM' | head -n 30
