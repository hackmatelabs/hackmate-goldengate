#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native/firmware
echo "netboot1 at 0x4C28100:"
xxd -s 0x4C28100 -l 16 bootkc.md0size.uidfix.netboot1
echo "netboot7 at 0x4C28100:"
xxd -s 0x4C28100 -l 16 bootkc.md0size.uidfix.netboot7
md5 bootkc.md0size.uidfix.netboot1
md5 bootkc.md0size.uidfix.netboot7
