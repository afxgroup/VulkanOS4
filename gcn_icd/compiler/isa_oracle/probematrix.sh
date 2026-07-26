#!/bin/sh
# One-instruction probes across all GCN targets. TSV: probe target status hexbytes error
TARGETS="gfx600 gfx601 gfx602 gfx700 gfx701 gfx702 gfx703 gfx704 gfx705 gfx801 gfx802 gfx803 gfx805 gfx810 gfx900 gfx902 gfx904 gfx906 gfx908 gfx909 gfx90a gfx90c"
for f in /s/probe/*.s; do
  b=$(basename "$f" .s)
  for t in $TARGETS; do
    if clang -x assembler -target amdgcn-- -mcpu=$t -c "$f" -o /tmp/p.o 2>/tmp/p.err; then
      llvm-objcopy -O binary --only-section=.text /tmp/p.o /tmp/p.bin 2>/dev/null
      if [ -s /tmp/p.bin ]; then
        hx=$(od -An -tx4 -v /tmp/p.bin | tr -s ' ' | tr -d '\n' | sed 's/^ //;s/ $//')
        printf '%s\t%s\tOK\t%s\t-\n' "$b" "$t" "$hx"
      else
        printf '%s\t%s\tEMPTYTEXT\t-\t-\n' "$b" "$t"
      fi
    else
      e=$(grep -m1 'error:' /tmp/p.err | sed 's/^.*error: //' | tr '\t' ' ')
      [ -z "$e" ] && e=$(head -c 120 /tmp/p.err | tr '\n\t' '  ')
      printf '%s\t%s\tFAIL\t-\t%s\n' "$b" "$t" "$e"
    fi
  done
done
