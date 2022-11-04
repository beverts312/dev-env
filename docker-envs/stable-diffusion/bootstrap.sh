#!/bin/bash +x
set -e
eval "$($CONDA_DIR/bin/conda shell.bash hook)"
conda activate ldm
exec "$@"
