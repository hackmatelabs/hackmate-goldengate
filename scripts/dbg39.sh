#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'memory read -s 4 -f x -c 2 0xfffffe002bc2d954' 'memory read -s 4 -f x -c 2 0xfffffe002bc2811c' 'detach' 'quit' > /tmp/gdb17.cmds
lldb -b -s /tmp/gdb17.cmds > /tmp/gg_gdb17.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
