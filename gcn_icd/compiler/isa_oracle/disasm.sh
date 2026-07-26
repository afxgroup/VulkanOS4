#!/bin/sh
# Disassemble one source across the three representative levels, side by side.
b=$1
for t in gfx600 gfx700 gfx803 gfx900; do
  echo "===== $b @ $t ====="
  clang -x assembler -target amdgcn-- -mcpu=$t -c /s/src/$b.s -o /tmp/x.o 2>/tmp/x.err || { echo "FAIL:"; cat /tmp/x.err; continue; }
  llvm-objdump -d --mcpu=$t /tmp/x.o | sed -n '/<.text>/,$p' | grep -v '^$'
done
