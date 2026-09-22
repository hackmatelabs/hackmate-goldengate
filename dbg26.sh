#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bb9be00 -c 18' 'disassemble -s 0xfffffe002bc55a80 -c 25' 'detach' 'quit' > /tmp/gdb10.cmds
lldb -b -s /tmp/gdb10.cmds > /tmp/gg_gdb10.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
