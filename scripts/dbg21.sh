#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bc28048 -c 40' 'disassemble -s 0xfffffe002bc29300 -c 70' 'detach' 'quit' > /tmp/gdb8.cmds
lldb -b -s /tmp/gdb8.cmds > /tmp/gg_gdb8.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
