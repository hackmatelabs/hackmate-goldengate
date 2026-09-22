#!/bin/zsh
# Start gdbstub on demand (does not stop VM until a client connects)
echo gdbserver | nc -U /tmp/gg_diag.sock -w 5 | tail -n 2
sleep 2
# lldb command file
printf '%s\n' 'gdb-remote 127.0.0.1:1234' 'bt 25' 'detach' 'quit' > /tmp/gdb.cmds
cat /tmp/gdb.cmds
timeout 60 lldb -b -s /tmp/gdb.cmds > /tmp/gg_gdbbt.txt 2>&1
echo "lldb rc: $?"
# make sure VM is resumed even if detach failed
echo cont | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
echo info status | nc -U /tmp/gg_diag.sock -w 5 | tail -n 1
