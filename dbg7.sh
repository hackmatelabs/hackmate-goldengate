#!/bin/zsh
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'bt 25' 'detach' 'quit' > /tmp/gdb.cmds
lldb -b -s /tmp/gdb.cmds > /tmp/gg_gdbbt.txt 2>&1
echo "lldb rc: $?"
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
