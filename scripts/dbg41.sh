#!/bin/zsh
otool -arch arm64e -tv /Users/raahimsyed/bs-early-tasks > /Users/raahimsyed/bs_dis2.txt 2>&1
wc -l /Users/raahimsyed/bs_dis2.txt
grep -n -e '0000000100000c00' -e '0000000100000c04' -e '0000000100000c08' -e '0000000100000c10' -e '0000000100000c40' /Users/raahimsyed/bs_dis2.txt | head -n 20
