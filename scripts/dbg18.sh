#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'register read sp x20' 'memory read -f x -c 40 `$sp - 256`' 'memory read -f x -c 40 `$sp + 0`' 'detach' 'quit' > /tmp/gdb5.cmds
lldb -b -s /tmp/gdb5.cmds > /tmp/gg_gdb5.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
