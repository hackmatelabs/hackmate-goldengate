#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bc291f0 -c 75' 'disassemble -s 0xfffffe002bc29440 -c 30' 'detach' 'quit' > /tmp/gdb9.cmds
lldb -b -s /tmp/gdb9.cmds > /tmp/gg_gdb9.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
