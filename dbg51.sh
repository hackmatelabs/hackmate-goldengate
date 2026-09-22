#!/bin/zsh
grep -a -m1 -e 'panic.cpu' /tmp/gg_diag_serial.log | cut -c1-200
