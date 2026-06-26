#!/usr/bin/env bash
# Enju task: chunk — delegates to bioyoda2.sh (the stage logic). Reads ENJU_PARAM_* for snapshot/collection/mode.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
exec ./bioyoda2.sh build compounds chunk --prod
