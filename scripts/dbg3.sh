#!/bin/zsh
PID=$(pgrep -f gg_diag.sock | head -n 1)
echo "qemu pid: $PID"
sample "$PID" 8 -f /tmp/gg_sample.txt 2>&1 | tail -n 3
ls -la /tmp/gg_sample.txt 2>/dev/null
