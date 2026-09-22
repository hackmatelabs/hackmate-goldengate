#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bc291ec -c 70' 'disassemble -s 0xfffffe002bc2d980 -c 20' 'disassemble -s 0xfffffe002bc282cc -c 60' 'detach' 'quit' > /tmp/gdb4.cmds
lldb -b -s /tmp/gdb4.cmds > /tmp/gg_gdb4.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
