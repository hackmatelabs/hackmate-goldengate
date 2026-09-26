#!/bin/zsh
cd /Users/raahimsyed/goldengate/qemu-sptm-cl4-native
wc -l hw/arm/xnu_patch.c
sed -n '94,220p' hw/arm/xnu_patch.c
