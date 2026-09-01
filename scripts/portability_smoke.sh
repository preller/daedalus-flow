#!/usr/bin/env bash
# Installs the built wheel into a clean venv outside the Nix dev shell, with
# LD_LIBRARY_PATH unset, and runs import, dae --help, dae example minimal and
# dae lab run. The [demo] extra's numpy import is reported, not asserted.

# Usage: scripts/portability_smoke.sh   (from the repo root)

# Run it after a change to the runtime dependency set or before a release.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

work="$(mktemp -d)"
venv="$work/venv"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

banner() { printf '\n========== %s ==========\n' "$1"; }

banner "build wheel (uv build)"
# Build into a fresh dist dir; a stale wheel cannot be picked up.
dist="$work/dist"
uv build --wheel --out-dir "$dist"
wheel="$(ls "$dist"/daedalus_flow-*.whl)"
echo "built: $wheel"

banner "create shim-free venv"
# The venv and every later command run with LD_LIBRARY_PATH unset. python3 is
# whatever is on PATH; the lean path must not care which loader it is.
env -u LD_LIBRARY_PATH python3 -m venv "$venv"
py="$venv/bin/python"
dae="$venv/bin/dae"

# Runs a command with the shim unset.
run() { env -u LD_LIBRARY_PATH "$@"; }

banner "install lean wheel (no extras)"
run "$py" -m pip install --quiet --upgrade pip
run "$py" -m pip install --quiet "$wheel"

banner "lean path: import + CLI journey (shim-free)"
run "$py" -c "import daedalus; print('import daedalus OK', daedalus.__name__)"
run "$dae" --help >/dev/null
echo "dae --help OK"

lab_parent="$work/labs"
mkdir -p "$lab_parent"
# Subshell cd, not `env -C`: BSD env on macOS (a target OS here) has no -C flag.
( cd "$lab_parent" && run "$dae" example minimal )
test -f "$lab_parent/minimal/lab.yaml"
echo "dae example minimal OK"
( cd "$lab_parent/minimal" && run "$dae" lab run )
echo "dae lab run OK"

# numpy must be absent from the base install.
if run "$py" -c "import numpy" 2>/dev/null; then
  echo "FAIL: numpy present in the lean (no-extra) install; default closure is not lean"
  exit 1
fi
echo "lean closure confirmed (numpy absent)"

banner "LEAN PORTABILITY: PASS (clean install runs shim-free)"

banner "best-effort: install [demo] extra + import numpy"
# Not fatal. On a Nix-store interpreter numpy needs the shim that is unset here;
# on a stock host this leg passes and covers the compiled wheel too.
demo_status="DEFER"
if run "$py" -m pip install --quiet "${wheel}[demo]" \
   && run "$py" -c "import numpy; print('import numpy OK', numpy.__version__)"; then
  demo_status="PASS"
fi
banner "DEMO (numpy) leg: $demo_status"

banner "SMOKE COMPLETE: lean PASS; demo leg $demo_status"
