#!/bin/zsh
# exp42: QD saturation sweep, Mac internal AP0512Z, O_DIRECT-ish (F_NOCACHE), posixaio
# Interleaved design: rep-major, QD arms alternated within each rep (sweep.c methodology)
set -e
cd /tmp/warp-exp42
BS=12406784
FILES=""
for i in $(seq 0 15); do FILES="$FILES:/tmp/warp-exp42/lane$i.bin"; done
FILES=${FILES#:}

run_arm () {
  local rep=$1 qd=$2
  fio --name=qd$qd \
      --filename=$FILES \
      --rw=read --bs=$BS --size=496271360 --iodepth=$qd \
      --ioengine=posixaio --direct=1 \
      --numjobs=16 --group_reporting \
      --minimal 2>/dev/null > arm_r${rep}_qd${qd}.csv
}

for rep in 1 2 3; do
  for qd in 1 2 4 8 16; do
    run_arm $rep $qd
    echo "done rep=$rep qd=$qd $(date +%H:%M:%S)"
  done
done
echo ALLDONE
