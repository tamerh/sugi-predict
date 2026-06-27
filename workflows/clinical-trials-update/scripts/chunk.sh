#!/usr/bin/env bash
# Enju task: chunk — delegates to bioyoda.sh build trials chunk (the stage logic; single source of truth).
# mode via ENJU_PARAM_mode (full|delta). embed reads POD_HOST/POD_PORT/POD_KEY for the GPU pod if set.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
MODE_FLAG=""; [[ "${ENJU_PARAM_mode:-delta}" == "full" ]] && MODE_FLAG="--full"
exec ./bioyoda.sh build trials chunk --prod $MODE_FLAG
