#!/bin/sh
# Differential assembly: every .s in $1 across every target in TARGETS.
# Emits TSV: source<TAB>target<TAB>status<TAB>textbytes<TAB>sha256<TAB>errfirstline
SRCDIR=${1:-/s/src}
OUT=${2:-/s/out}
TARGETS="gfx600 gfx601 gfx602 gfx700 gfx701 gfx702 gfx703 gfx704 gfx705 gfx801 gfx802 gfx803 gfx805 gfx810 gfx900 gfx902 gfx904 gfx906 gfx908 gfx909 gfx90a gfx90c"
mkdir -p "$OUT"
for f in "$SRCDIR"/*.s; do
  b=$(basename "$f" .s)
  for t in $TARGETS; do
    o="$OUT/$b.$t.o"; bin="$OUT/$b.$t.bin"; err="$OUT/$b.$t.err"
    rm -f "$o" "$bin"
    if clang -x assembler -target amdgcn-- -mcpu=$t -c "$f" -o "$o" 2>"$err"; then
      llvm-objcopy -O binary --only-section=.text "$o" "$bin" 2>>"$err" || true
      if [ -s "$bin" ]; then
        sz=$(wc -c < "$bin" | tr -d ' ')
        h=$(sha256sum "$bin" | cut -c1-16)
        printf '%s\t%s\tOK\t%s\t%s\t-\n' "$b" "$t" "$sz" "$h"
      else
        printf '%s\t%s\tEMPTYTEXT\t0\t-\t-\n' "$b" "$t"
      fi
    else
      e=$(grep -m1 'error:' "$err" | sed 's/^.*error: //' | tr '\t' ' ')
      printf '%s\t%s\tFAIL\t-\t-\t%s\n' "$b" "$t" "$e"
    fi
  done
done
