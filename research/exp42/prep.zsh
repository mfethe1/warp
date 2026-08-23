#!/bin/zsh
# exp42 prep: create 16 lane files (40 x 12406784B blocks each) using fio itself.
# fio write phase: numjobs=16, each job writes its own lane file (fio auto-names filename=lane<N>.bin)
set -e
cd /tmp/warp-exp42
fio --name=prep \
    --ioengine=io_uring \
    --rw=write \
    --bs=12406784 \
    --size=496271360 \
    --numjobs=16 \
    --direct=1 \
    --filename=lane \
    --allow_file_create=1 \
    --fallocate=none \
    --iodepth=8 \
    --group_reporting \
    --minimal \
    > prep.log 2>&1 || fio --name=prep --rw=write --bs=12406784 --size=496271360 --numjobs=16 --direct=1 --filename=lane --allow_file_create=1 --iodepth=8 --group_reporting --minimal > prep2.log 2>&1
ls -l /tmp/warp-exp42/
