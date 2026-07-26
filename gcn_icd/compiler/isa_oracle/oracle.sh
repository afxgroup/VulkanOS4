#!/bin/sh
# GCN per-generation encoding oracle. Run INSIDE the silkeh/clang container:
#   MSYS_NO_PATHCONV=1 docker run --rm -v "<scratchpad>:/s" -w /s silkeh/clang:latest sh /s/oracle.sh
# Expects /s/src/*.s (copies of the project's gfx8 shader sources) and the
# helper scripts matrix.sh probematrix.sh genprobes.py genprobes2.py reduce.py
# deltas.py dwdiff.py units.ll alongside.
set -e
cd /s
echo "############ 0. toolchain"
clang --version | head -2
echo "############ 0b. targets recognised (mach flag; 0x0 == NOT recognised)"
printf '.text\n    s_endpgm\n' > /tmp/e.s
for t in gfx600 gfx601 gfx602 gfx700 gfx701 gfx702 gfx703 gfx704 gfx705 \
         gfx801 gfx802 gfx803 gfx805 gfx810 \
         gfx900 gfx902 gfx904 gfx906 gfx908 gfx909 gfx90a gfx90c BOGUS999; do
  clang -x assembler -target amdgcn-- -mcpu=$t -c /tmp/e.s -o /tmp/e.o 2>/dev/null
  printf '%-10s %s\n' "$t" "$(llvm-readelf -h /tmp/e.o | sed -n 's/^ *Flags: *//p')"
done

echo "############ 1. real-shader differential assembly"
sh /s/matrix.sh /s/src /s/out > /s/matrix.tsv
awk -F'\t' '{print $3}' /s/matrix.tsv | sort | uniq -c
awk -F'\t' '$3=="OK"{a[$1"\t"$5]=a[$1"\t"$5]","substr($2,4); s[$1"\t"$5]=$4}
  END{for(k in a){split(k,p,"\t"); printf "%-17s %-5s %s\n",p[1],s[k],substr(a[k],2)}}' /s/matrix.tsv | sort

echo "############ 2. one-instruction probes + per-generation deltas"
python3 /s/genprobes.py  && sh /s/probematrix.sh > /s/probe.tsv
python3 /s/genprobes2.py && sh /s/probematrix.sh > /s/probe2.tsv
python3 /s/deltas.py /s/probe.tsv /s/probe2.tsv

echo "############ 3. SMEM offset UNITS via LLVM's own code generator"
echo "   (same IR, byte offset 128 -> 0x20 means DWORD units, 0x80 means BYTE units)"
for t in gfx600 gfx700 gfx803 gfx900; do
  printf '%-8s %s\n' "$t" \
    "$(llc -mtriple=amdgcn-- -mcpu=$t /s/units.ll -o - \
       | sed -n '/^off128:/,/End function/p' | sed -n 's/^\t\(s_load_dword s0, s\[0:1\].*\)/\1/p')"
done
echo "   and the same for offsets 1020 / 1024 / 4096 bytes (units2.ll):"
for t in gfx600 gfx700 gfx803 gfx900; do
  printf '   %-8s' "$t"
  for fn in off1020 off1024 off4096; do
    printf ' %s=[%s]' "$fn" \
      "$(llc -mtriple=amdgcn-- -mcpu=$t /s/units2.ll -o - \
         | sed -n "/^$fn:/,/End function/p" | sed -n 's/^\t\(s_load_dword s0, s\[0:1\], \)//p' | head -1)"
  done; echo
done

echo "############ 4. instrument controls"
echo "-- .text section size must match extracted .bin --"
llvm-readelf -S /s/out/ps_solid.gfx803.o | grep ' .text'
echo "   ps_solid.gfx803.bin bytes = $(wc -c < /s/out/ps_solid.gfx803.bin)  (expect 28 = 0x1c)"
echo "-- no silently-empty .text anywhere --"
grep -c EMPTYTEXT /s/matrix.tsv /s/probe.tsv /s/probe2.tsv || true
echo "-- a 1-instruction source change must be detected as DIFFERENT --"
sed 's/v_mov_b32 v1, 0/v_mov_b32 v1, 1.0/' /s/src/ps_solid.s > /tmp/ctl.s
for t in gfx600 gfx803; do
  clang -x assembler -target amdgcn-- -mcpu=$t -c /s/src/ps_solid.s -o /tmp/a.o
  clang -x assembler -target amdgcn-- -mcpu=$t -c /tmp/ctl.s -o /tmp/b.o
  llvm-objcopy -O binary --only-section=.text /tmp/a.o /tmp/a.bin
  llvm-objcopy -O binary --only-section=.text /tmp/b.o /tmp/b.bin
  printf '   %-8s %s\n' "$t" "$(cmp -s /tmp/a.bin /tmp/b.bin && echo 'SAME (BUG!)' || echo 'DIFFERENT (good)')"
done
echo "############ done"
