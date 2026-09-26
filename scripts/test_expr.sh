#!/bin/bash
opt="--target-list=aarch64-softmmu"
optarg=$(expr "x$opt" : 'x[^=]*=\(.*\)')
echo "RESULT: [$optarg]"
