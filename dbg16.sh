#!/bin/zsh
echo "=== CPU lines in no-icount boot serial ==="
grep -a -i -e 'cpu_start' -e 'processor' -e 'PE_cpu' -e 'cluster' -e 'Cores:' -e 'ncpu' -e 'cpu_count' -e 'bringing up' -e 'started cpu' /tmp/gg_diag_serial.log | head -n 25
echo "=== serial size / tail ==="
wc -c /tmp/gg_diag_serial.log
tail -n 2 /tmp/gg_diag_serial.log | cut -c1-150
