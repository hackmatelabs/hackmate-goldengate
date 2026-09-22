#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'register read x19 x20 x21' 'disassemble -s 0xfffffe002bc29140 -c 45' 'disassemble -s 0xfffffe002bc2821c -c 45' 'disassemble -s 0xfffffe002bc297e4 -c 35' 'detach' 'quit' > /tmp/gdb3.cmds
lldb -b -s /tmp/gdb3.cmds > /tmp/gg_gdb3.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
