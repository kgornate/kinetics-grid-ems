#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-python3}
"$PYTHON" -m compileall -q app
"$PYTHON" tools/run_elecod_lineage_sil.py --power-kw "${SIL_POWER_KW:-20}"
"$PYTHON" -m pytest -q
