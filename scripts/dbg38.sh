#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'br set -a 0xfffffe002bc29140' 'c' 'register read x1' 'c' 'register read x1' 'c' 'register read x1' 'c' 'register read x1' 'c' 'register read x1' 'detach' 'quit' > /tmp/gdb16.cmds
lldb -b -s /tmp/gdb16.cmds > /tmp/gg_gdb16.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
