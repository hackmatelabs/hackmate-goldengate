#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'memory write -s 4 0xfffffe002bc2d954 0x52800021' 'memory write -s 4 0xfffffe002bc2811c 0x52800021' 'memory read -s 4 -f x -c 1 0xfffffe002bc2d954' 'memory read -s 4 -f x -c 1 0xfffffe002bc2811c' 'detach' 'quit' > /tmp/gdb18.cmds
lldb -b -s /tmp/gdb18.cmds > /tmp/gg_gdb18.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
