#!/bin/bash
MODEL_BASE=${1}
TASK="$(cut -d '-' -f 1 <<< "$MODEL_BASE")"

python3 maxim/run_eval.py \
    --ckpt_path ./pretrained/${MODEL_BASE}.npz \
    --input_dir ../working \
    --output_dir ../working \
    --has_target=False \
    --task $TASK
