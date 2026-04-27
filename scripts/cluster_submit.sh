#!/usr/bin/env bash
# Submit one LSF job per crop. Designed for Janelia (LSF) but can be adapted
# to any HPC scheduler.
#
# Usage:
#   cd /path/to/ecs-analysis
#   export ECS_DATA_BASE=/nrs/cellmap/data
#   export ECS_PYTHON=/path/to/python  # python with deps installed
#   bash scripts/cluster_submit.sh native        # phase 2 (all metrics)
#   bash scripts/cluster_submit.sh matched       # phase 4 (downsampled to 8nm)
#   bash scripts/cluster_submit.sh degradation   # phase 5 (Chemical scan)
#   bash scripts/cluster_submit.sh topology      # just topology, all crops
#
# Resource hints (LSF -W is wall-clock minutes, -n is core count):
#   - Topology native at 2nm: 90 min, 2 cores, 16G RAM
#   - Topology matched at 8nm: 30 min, 2 cores, 8G RAM
#   - Fast metrics: 15 min, 1 core, 8G RAM
#
# Each job appends its row to results/<phase>_<metric>.csv via the runner's
# incremental-write logic. After all jobs complete, run:
#   python -m scripts.summarize --prefix native
#   python -m scripts.make_figures --prefix native

set -e

PHASE="${1:?usage: $0 <native|matched|degradation|topology>}"
ECS_PYTHON="${ECS_PYTHON:-python3}"
ECS_DATA_BASE="${ECS_DATA_BASE:-/nrs/cellmap/data}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Resource defaults — tune for your cluster. Janelia LSF flags shown.
QUEUE="${ECS_QUEUE:-local}"        # or short, normal, gpu_rtx
TIME_MIN="${ECS_TIME_MIN:-180}"
CORES="${ECS_CORES:-2}"
MEM_MB="${ECS_MEM_MB:-16000}"

# Build crop list from the package's config (single source of truth).
CROPS=$("$ECS_PYTHON" - <<'PY'
from ecs import config
print(' '.join(c.crop for c in config.active_crops()))
PY
)

LOG_DIR="$REPO_ROOT/cluster_logs/$PHASE"
mkdir -p "$LOG_DIR"

case "$PHASE" in
    native)      MODULE="scripts.run_native";        FLAGS="" ;;
    matched)     MODULE="scripts.run_matched";       FLAGS="" ;;
    degradation) MODULE="scripts.run_degradation";   FLAGS="--prep Chemical" ;;
    topology)    MODULE="scripts.run_native";        FLAGS="--metrics topology" ;;
    *) echo "Unknown phase: $PHASE"; exit 1 ;;
esac

for crop in $CROPS; do
    JOB_NAME="ecs_${PHASE}_${crop}"
    OUT_LOG="$LOG_DIR/${crop}.out"
    ERR_LOG="$LOG_DIR/${crop}.err"
    bsub -q "$QUEUE" -W "$TIME_MIN" -n "$CORES" \
         -R "rusage[mem=$MEM_MB] span[hosts=1]" \
         -J "$JOB_NAME" \
         -o "$OUT_LOG" -e "$ERR_LOG" \
         "cd $REPO_ROOT && \
          export ECS_DATA_BASE=$ECS_DATA_BASE && \
          $ECS_PYTHON -u -m $MODULE --only $crop $FLAGS"
done

echo "Submitted $(echo $CROPS | wc -w) jobs for phase=$PHASE"
echo "Logs: $LOG_DIR"
echo "Watch: bjobs -w | grep ecs_${PHASE}"
