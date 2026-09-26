#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'register read x19 x20' 'memory read -f x -c 48 `$x19 - 128`' 'detach' 'quit' > /tmp/gdb12.cmds
lldb -b -s /tmp/gdb12.cmds > /tmp/gg_gdb12.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
