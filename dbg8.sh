#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bc2d8e0 -c 60' 'disassemble -s 0xfffffe002bc2d580 -c 20' 'si' 'si' 'si' 'si' 'si' 'si' 'si' 'si' 'bt 5' 'detach' 'quit' > /tmp/gdb2.cmds
lldb -b -s /tmp/gdb2.cmds > /tmp/gg_gdb2.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
