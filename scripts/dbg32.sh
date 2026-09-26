#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'memory read -s 4 -f x -c 4 0xfffffe002bc28110' 'detach' 'quit' > /tmp/gdb13.cmds
lldb -b -s /tmp/gdb13.cmds > /tmp/gg_gdb13.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
