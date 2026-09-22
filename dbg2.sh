#!/bin/zsh
PID=$(pgrep -f gg_diag.sock | head -n 1)
echo "qemu pid: $PID"
which lldb
sudo -n true 2>&1 | head -n 1
echo "attaching..."
lldb -b -p "$PID" -o 'thread backtrace all' -o detach -o quit > /tmp/gg_hostbt.txt 2>&1
echo "lldb rc: $?"
grep -c '^' /tmp/gg_hostbt.txt
