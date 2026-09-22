#!/bin/zsh
echo "=== serial size ==="
wc -c /tmp/gg_diag_serial.log
echo "=== SEP/endpoint/wait lines ==="
grep -a -i -e 'SEP' -e 'endpoint' -e 'Waiting' -e 'waitFor' -e 'timeout' /tmp/gg_diag_serial.log | head -n 25
echo "=== tail ==="
tail -n 2 /tmp/gg_diag_serial.log | cut -c1-150
