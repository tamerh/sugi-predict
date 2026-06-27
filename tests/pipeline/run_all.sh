#!/usr/bin/env bash
# Run all tier-1 pipeline tests (small fixtures, no prod, no GPU). Exits non-zero if any fail.
# Each test runs the real `bioyoda.sh build <collection>` in test mode -> *_test collection -> asserts.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x /data/miniconda3/envs/bioyoda/bin/python ]]; then PY=/data/miniconda3/envs/bioyoda/bin/python; else PY=python3; fi

# fastest first (reference ~20s, then the embed tests ~1-2min, compounds last ~2-3min)
TESTS=(test_build_reference.py test_build_text.py test_build_trials.py test_build_proteins.py test_build_compounds.py)
fail=0
for t in "${TESTS[@]}"; do
  echo "================ $t ================"
  if ! "$PY" "$HERE/$t"; then echo "FAILED: $t"; fail=1; fi
done
[[ $fail -eq 0 ]] && echo "ALL PIPELINE TESTS PASSED" || echo "SOME PIPELINE TESTS FAILED"
exit $fail
