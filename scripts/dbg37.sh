#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'br set -a 0xfffffe002bc29140' 'c' 'register read x0 x1 x2 x30 x29' 'memory read -f x -c 24 `$x0 - 32`' 'memory read -f x -c 24 `$x1 - 32`' 'detach' 'quit' > /tmp/gdb15.cmds
lldb -b -s /tmp/gdb15.cmds > /tmp/gg_gdb15.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
