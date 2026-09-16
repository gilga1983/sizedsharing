#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="${UPSTREAM_REPO:-https://github.com/ohadeytan/caffeine.git}"
UPSTREAM_REF="${UPSTREAM_REF:-arXiv_submission}"
LAMBDAS="${LAMBDAS:-0.25 0.50 0.75 1.00 1.25 1.50 2.00 3.00 4.00}"
CAPACITY_FRACTIONS="${CAPACITY_FRACTIONS:-0.005 0.01 0.02 0.05 0.10 0.20 0.40}"
REQUESTS=1000000
TRACE=""
DOWNLOAD_WIKI=0

usage() {
  echo "Usage: $0 [--trace FILE] [--download-wiki] [--requests N]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trace) TRACE="$2"; shift 2 ;;
    --download-wiki) DOWNLOAD_WIKI=1; shift ;;
    --requests) REQUESTS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1"; usage; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/work"
RESULTS="$ROOT/results"
mkdir -p "$WORK" "$RESULTS"

if [[ $DOWNLOAD_WIKI -eq 1 ]]; then
  TRACE="$WORK/wiki2018_${REQUESTS}.tr"
  if [[ ! -s "$TRACE" ]]; then
    echo "[trace] extracting first ${REQUESTS} requests of Wiki2018"
    ARCHIVE="$WORK/wiki2018.tr.tar.gz"
    if [[ ! -s "$ARCHIVE" ]]; then
      curl -L --fail --retry 3 \
        -o "$ARCHIVE" \
        "http://lrb.cs.princeton.edu/wiki2018.tr.tar.gz"
    fi
    MEMBER="$(tar -tzf "$ARCHIVE" | head -n 1)"
    tar -xOzf "$ARCHIVE" "$MEMBER" | head -n "$REQUESTS" > "$TRACE" || true
    test -s "$TRACE"
  fi
fi

if [[ -z "$TRACE" || ! -s "$TRACE" ]]; then
  echo "A trace is required. Use --trace FILE or --download-wiki."
  exit 2
fi
TRACE="$(cd "$(dirname "$TRACE")" && pwd)/$(basename "$TRACE")"

SRC="$WORK/caffeine"
if [[ ! -d "$SRC/.git" ]]; then
  git clone "$UPSTREAM_REPO" "$SRC"
fi
git -C "$SRC" fetch origin "$UPSTREAM_REF"
git -C "$SRC" checkout -f "$UPSTREAM_REF"
git -C "$SRC" reset --hard "origin/$UPSTREAM_REF" 2>/dev/null || true
git -C "$SRC" clean -fdx

echo "[patch] applying capacity-conditioned AV"
git -C "$SRC" apply "$ROOT/capacity_conditioned_av.patch"

# Compute the unique-byte footprint using the last observed size for each object id.
read -r UNIQUE_BYTES REQUEST_COUNT <<< "$(python3 - "$TRACE" <<'PY'
import sys
path = sys.argv[1]
sizes = {}
n = 0
with open(path, "rt", errors="replace") as f:
    for line in f:
        p = line.split()
        if len(p) < 3:
            continue
        try:
            k = int(p[1]); s = int(p[2])
        except ValueError:
            continue
        sizes[k] = s
        n += 1
print(sum(sizes.values()), n)
PY
)"

echo "[trace] requests=$REQUEST_COUNT unique_bytes=$UNIQUE_BYTES"

CAP_META="$RESULTS/capacities.csv"
echo "fraction,capacity_bytes" > "$CAP_META"
for F in $CAPACITY_FRACTIONS; do
  CAP="$(python3 - "$UNIQUE_BYTES" "$F" <<'PY'
import sys
u = int(sys.argv[1]); f = float(sys.argv[2])
print(max(1, int(round(u * f))))
PY
)"
  echo "$F,$CAP" >> "$CAP_META"
done

COMMON=(
  "-Dcaffeine.simulator.files.format=adapt-size"
  "-Dcaffeine.simulator.files.paths.0=$TRACE"
  "-Dcaffeine.simulator.policies.0=sketch.SumSizedWindowTinyLfu"
  "-Dcaffeine.simulator.admission.0=Always"
  "-Dcaffeine.simulator.sized-window-tiny-lfu.scaled=false"
  "-Dcaffeine.simulator.sized-window-tiny-lfu.bump=true"
  "-Dcaffeine.simulator.sized-window-tiny-lfu.prune=true"
  "-Dcaffeine.simulator.window-tiny-lfu.percent-main.0=0.99"
  "-Dcaffeine.simulator.report.format=csv"
  "-Dcaffeine.simulator.report.ascending=false"
)

echo "[build] compiling simulator once"
(cd "$SRC" && ./gradlew simulator:classes)

while IFS=, read -r F CAP; do
  [[ "$F" == "fraction" ]] && continue
  for L in $LAMBDAS; do
    TAG="f${F}_c${CAP}_l${L}"
    OUT="$RESULTS/${TAG}.csv"
    echo "[run] fraction=$F capacity=$CAP lambda=$L"
    (
      cd "$SRC"
      ./gradlew simulator:run -q \
        "${COMMON[@]}" \
        "-Dcaffeine.simulator.maximum-size=$CAP" \
        "-Dcaffeine.simulator.sized-window-tiny-lfu.admission-multiplier=$L" \
        "-Dcaffeine.simulator.report.output=$OUT"
    )
    printf '{"fraction": %s, "capacity_bytes": %s, "lambda": %s, "csv": "%s"}\n' \
      "$F" "$CAP" "$L" "$(basename "$OUT")" > "$RESULTS/${TAG}.json"
  done
done < "$CAP_META"

echo
echo "Sweep complete."
echo "Analyze with: python3 \"$ROOT/analyze.py\" \"$RESULTS\""
