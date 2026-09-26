#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'memory read -f x -c 16 0xfffffe913670bf20' 'memory read -f x -c 32 0xfffffe913670bf40' 'disassemble -s 0xfffffe002bc2d880 -c 14' 'detach' 'quit' > /tmp/gdb6.cmds
lldb -b -s /tmp/gdb6.cmds > /tmp/gg_gdb6.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
