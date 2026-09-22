#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'br set -a 0xfffffe002bc29140' 'c' 'register read x0 x1 x2 x19 x20' 'bt 8' 'detach' 'quit' > /tmp/gdb14.cmds
lldb -b -s /tmp/gdb14.cmds > /tmp/gg_gdb14.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
