#!/usr/bin/env bash
# Enju task: denoise — delegates to bioyoda.sh (the stage logic). Reads ENJU_PARAM_* for snapshot/collection/mode.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec ./bioyoda.sh build compounds denoise --prod
