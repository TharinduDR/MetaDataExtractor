#!/bin/bash
#SBATCH -p gpu-medium
#SBATCH --gres=gpu:nvidia_h200_nvl:2
#SBATCH --mem=100G
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=32
#SBATCH --job-name=acl-array
#SBATCH -o logs/gpu-%A_%a.out
#SBATCH -e logs/gpu-%A_%a.err

set -uo pipefail

URL_LIST="${URL_LIST:-volume_urls.txt}"
OUTPUT_ROOT="${OUTPUT_ROOT:-output}"
DONE_DIR="${DONE_DIR:-done}"
mkdir -p "$OUTPUT_ROOT" "$DONE_DIR" logs

# Pick this task's URL = line number == array index.
url="$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$URL_LIST")"
if [[ -z "$url" ]]; then
    echo "No URL on line ${SLURM_ARRAY_TASK_ID} of ${URL_LIST}; nothing to do."
    exit 0
fi

vol_id="$(echo "$url" | sed -E 's#.*/volumes/([^/]+)/?#\1#')"
marker="${DONE_DIR}/${vol_id}.done"

if [[ -f "$marker" ]]; then
    echo "[$(date)] SKIP  $vol_id (already done)"
    exit 0
fi

source /etc/profile
module add anaconda3/2023.09
module add cuda/12.0
source activate /storage/hpc/37/ranasint/conda_envs/llm_exp
export HF_HOME=/scratch/hpc/37/ranasint/hf_cache
export HF_TOKEN=

echo "[$(date)] START task ${SLURM_ARRAY_TASK_ID}: $vol_id -> $url"
if python batch_extract.py "$url" \
        --output_dir "${OUTPUT_ROOT}/${vol_id}" \
        --qwen_device cuda:0 --gemma_device cuda:1 --thinking_device auto; then
    touch "$marker"
    echo "[$(date)] DONE  $vol_id"
else
    echo "[$(date)] FAIL  $vol_id (exit $?)" >&2
    exit 1
fi