#!/bin/zsh
printf '%s\n' 'x /1wx 0xfffffe002c9d61f0' 'x /1wx 0xfffffe002c9d62e0' 'x /4gx 0xfffffe002c9d6290' 'x /1gx 0xfffffe2412035bc8' 'x /1gx 0xfffffe002c9dd348' | nc -U /tmp/gg_diag.sock -w 8 | grep -a -e 'fffffe002c9d6' -e 'fffffe2412035bc8' -e 'fffffe002c9dd348'
