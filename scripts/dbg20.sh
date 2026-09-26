#!/bin/zsh
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
sleep 2
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'disassemble -s 0xfffffe002bb9be40 -c 30' 'disassemble -s 0xfffffe002bd7d9f0 -c 30' 'detach' 'quit' > /tmp/gdb7.cmds
lldb -b -s /tmp/gdb7.cmds > /tmp/gg_gdb7.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
