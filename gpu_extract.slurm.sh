#!/bin/bash
#SBATCH -p gpu-medium
#SBATCH --gres=gpu:nvidia_h200_nvl:2
#SBATCH --mem=100G
#SBATCH --time=48:00:00
#SBATCH --cpus-per-task=32
#SBATCH --job-name=acl-extract
#SBATCH -o logs/gpu-%j.out
#SBATCH -e logs/gpu-%j.err

set -euo pipefail

VOLUME_URL="${1:?Usage: sbatch gpu_extract.slurm <volume_url> [output_dir]}"
OUTPUT_DIR="${2:-./output}"

source /etc/profile
module add anaconda3/2023.09
module add cuda/12.0

source activate /storage/hpc/37/ranasint/conda_envs/llm_exp
export HF_HOME=/scratch/hpc/37/ranasint/hf_cache
export HF_TOKEN=

python batch_extract.py "$VOLUME_URL" \
    --output_dir "$OUTPUT_DIR" \
    --qwen_device cuda:0 --gemma_device cuda:1 --thinking_device auto