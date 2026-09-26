#!/bin/zsh
echo "--- serial size ---"
wc -c /tmp/gg_diag_serial.log
echo "--- jit stats 1 ---"
echo info jit | nc -U /tmp/gg_diag.sock -w 5 | grep -a -e 'tb count' -e 'translations' -e 'ops  ' | head -n 6
echo "--- pc 1 ---"
echo info registers | nc -U /tmp/gg_diag.sock -w 3 | grep -a PC=
sleep 45
echo "--- serial size ---"
wc -c /tmp/gg_diag_serial.log
echo "--- jit stats 2 ---"
echo info jit | nc -U /tmp/gg_diag.sock -w 5 | grep -a -e 'tb count' -e 'translations' | head -n 6
echo "--- pc 2 ---"
echo info registers | nc -U /tmp/gg_diag.sock -w 3 | grep -a PC=
echo "--- serial tail ---"
tail -n 2 /tmp/gg_diag_serial.log | cut -c1-150
