#!/bin/bash
#SBATCH -p serial          # your indefinite/long CPU queue — set this
#SBATCH --job-name=acl-orchestrator
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=30-00:00:00           # must outlive the sum of all GPU jobs; adjust
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=t.ranasinghe@lancaster.ac.uk
#SBATCH -o logs/orchestrator-%j.out
#SBATCH -e logs/orchestrator-%j.err

set -uo pipefail

URL_LIST="${1:-volume_urls.txt}"
GPU_SCRIPT="gpu_extract.slurm.sh"
OUTPUT_ROOT="output"
DONE_DIR="done"

mkdir -p "$OUTPUT_ROOT" "$DONE_DIR" logs

while IFS= read -r url || [[ -n "$url" ]]; do
    [[ -z "$url" || "$url" == \#* ]] && continue

    vol_id="$(echo "$url" | sed -E 's#.*/volumes/([^/]+)/?#\1#')"
    marker="${DONE_DIR}/${vol_id}.done"

    if [[ -f "$marker" ]]; then
        echo "[$(date)] SKIP  $vol_id"
        continue
    fi

    echo "[$(date)] START $vol_id -> $url"
    if sbatch --wait "$GPU_SCRIPT" "$url" "${OUTPUT_ROOT}/${vol_id}"; then
        touch "$marker"
        echo "[$(date)] DONE  $vol_id"
    else
        echo "[$(date)] FAIL  $vol_id (gpu job exited non-zero)" >&2
        echo "$vol_id" >> failed_volumes.txt
    fi
done < "$URL_LIST"

echo "[$(date)] Orchestrator finished."