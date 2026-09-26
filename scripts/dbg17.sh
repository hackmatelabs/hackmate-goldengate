#!/bin/zsh
echo "=== CPU lines in Sept20 installer boot ==="
grep -a -i -e 'cpu_start' -e 'failed to start cpu' -e 'processor' -e 'PE_cpu' -e 'Cores' -e 'ncpu' -e 'cpu_count' -e 'starting cpu' -e 'cpu_start_done' /tmp/gg_recprops_1789935575_serial.log | head -n 25
echo "=== pmu/cluster/aic lines ==="
grep -a -i -e 'aic' -e 'cluster' -e 'pmpm' -e 'AppleARMIODevice' /tmp/gg_recprops_1789935575_serial.log | head -n 15
