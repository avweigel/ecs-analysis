#!/usr/bin/env bash
# Submit one LSF job per crop. Designed for Janelia (LSF) but can be adapted
# to any HPC scheduler.
#
# Usage:
#   cd /path/to/ecs-analysis
#   pixi install                       # one-time, creates .pixi/envs/default
#   export ECS_DATA_BASE=/nrs/cellmap/data
#   # ECS_PYTHON auto-resolves to .pixi/envs/default/bin/python; override if needed
#   bash scripts/cluster_submit.sh native        # phase 2 (all metrics)
#   bash scripts/cluster_submit.sh matched       # phase 4 (downsampled to 8nm)
#   bash scripts/cluster_submit.sh degradation   # phase 5 (Chemical scan)
#   bash scripts/cluster_submit.sh topology      # just topology, all crops
#
# Resource hints (Janelia LSF: 1 slot = 1 core + 15 GB on the `local` queue;
# memory is *not* requested separately — it follows the core count).
#   - Heavy chemical/cortex crops (2-4nm): peak ~40 GB → -n 5 (75 GB)
#   - Topology matched at 8nm: ~10 GB → -n 1 (15 GB) plenty
#   - Fast metrics: ~few GB → -n 1
# `-W` is wall-clock minutes. `local` queue allows up to 14 days.
#
# Each job appends its row to results/<phase>_<metric>.csv via the runner's
# incremental-write logic. After all jobs complete, run:
#   python -m scripts.summarize --prefix native
#   python -m scripts.make_figures --prefix native

set -e

PHASE="${1:?usage: $0 <native|matched|degradation|topology>}"
ECS_DATA_BASE="${ECS_DATA_BASE:-/nrs/cellmap/data}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Resolve the python interpreter from the pixi environment. Override with
# ECS_PYTHON if you've installed deps some other way.
if [ -z "${ECS_PYTHON:-}" ]; then
    if [ -x "$REPO_ROOT/.pixi/envs/default/bin/python" ]; then
        ECS_PYTHON="$REPO_ROOT/.pixi/envs/default/bin/python"
    else
        echo "Pixi env not found at $REPO_ROOT/.pixi/envs/default — run 'pixi install' first," >&2
        echo "or set ECS_PYTHON to a python with requirements.txt installed." >&2
        exit 1
    fi
fi

# Resource defaults — tune for your cluster. Janelia LSF flags shown.
QUEUE="${ECS_QUEUE:-local}"        # or short (≤60min), gpu_*
PROJECT="${ECS_PROJECT:-cellmap}"  # LSF -P billing project
TIME_MIN="${ECS_TIME_MIN:-360}"
# On Janelia, RAM follows core count (15 GB/slot on CPU queues), so we
# pick CORES large enough to cover the worst-case crop. Empirically the
# heaviest cortex-chemical crops at 2nm peak at 80-90 GB during topology,
# so -n 8 (120 GB) is the safe default.
CORES="${ECS_CORES:-8}"

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
    bsub -P "$PROJECT" -q "$QUEUE" -W "$TIME_MIN" -n "$CORES" \
         -J "$JOB_NAME" \
         -o "$OUT_LOG" -e "$ERR_LOG" \
         "cd $REPO_ROOT && \
          export ECS_DATA_BASE=$ECS_DATA_BASE && \
          ${ECS_RESULTS_DIR:+export ECS_RESULTS_DIR=$ECS_RESULTS_DIR &&} \
          ${ECS_FIGURES_DIR:+export ECS_FIGURES_DIR=$ECS_FIGURES_DIR &&} \
          export OMP_NUM_THREADS=\$LSB_DJOB_NUMPROC && \
          export MKL_NUM_THREADS=\$LSB_DJOB_NUMPROC && \
          export OPENBLAS_NUM_THREADS=\$LSB_DJOB_NUMPROC && \
          export TBB_NUM_THREADS=\$LSB_DJOB_NUMPROC && \
          $ECS_PYTHON -u -m $MODULE --only $crop $FLAGS"
done

echo "Submitted $(echo $CROPS | wc -w) jobs for phase=$PHASE"
echo "Logs: $LOG_DIR"
echo "Watch: bjobs -w | grep ecs_${PHASE}"
