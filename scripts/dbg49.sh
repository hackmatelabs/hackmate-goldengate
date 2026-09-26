#!/bin/zsh
grep -a -m2 -e 'panic.' /tmp/gg_diag_serial.log | cut -c1-160
grep -a -m4 -e 'VIOLATION' /tmp/gg_diag_serial.log | cut -c1-160
