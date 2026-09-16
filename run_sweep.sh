#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="${UPSTREAM_REPO:-https://github.com/ohadeytan/caffeine.git}"
UPSTREAM_REF="${UPSTREAM_REF:-arXiv_submission}"
MODES="${MODES:-fixed elastic}"
CAPACITY_FRACTIONS="${CAPACITY_FRACTIONS:-0.005 0.01 0.02 0.05 0.10 0.20 0.40}"
REQUESTS=1000000
TRACE=""
DOWNLOAD_WIKI=0
SYNTHETIC=0

usage() {
  echo "Usage: $0 [--trace FILE | --synthetic | --download-wiki] [--requests N]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trace) TRACE="$2"; shift 2 ;;
    --synthetic) SYNTHETIC=1; shift ;;
    --download-wiki) DOWNLOAD_WIKI=1; shift ;;
    --requests) REQUESTS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1"; usage; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/work"
RESULTS="$ROOT/results"
mkdir -p "$WORK"
rm -rf "$RESULTS"
mkdir -p "$RESULTS"

if [[ $SYNTHETIC -eq 1 ]]; then
  TRACE="$WORK/synthetic_${REQUESTS}.tr"
  python3 "$ROOT/generate_synthetic.py" --output "$TRACE" --requests "$REQUESTS"
fi

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
  echo "A trace is required. Use --trace FILE, --synthetic, or --download-wiki."
  exit 2
fi
TRACE="$(cd "$(dirname "$TRACE")" && pwd)/$(basename "$TRACE")"

SRC="$WORK/caffeine"
if [[ ! -d "$SRC/.git" ]]; then
  git clone "$UPSTREAM_REPO" "$SRC"
fi
git -C "$SRC" fetch origin "$UPSTREAM_REF"
git -C "$SRC" checkout -B "$UPSTREAM_REF" "origin/$UPSTREAM_REF"
git -C "$SRC" clean -fdx

echo "[patch] applying checked minimal elastic-buffer transformation"
(cd "$SRC" && python3 "$ROOT/apply_experiment_patch.py")

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

APP_CONF="$SRC/simulator/src/main/resources/application.conf"

echo "[build] compiling patched simulator"
(cd "$SRC" && ./gradlew simulator:classes </dev/null)

while IFS=, read -r F CAP; do
  [[ "$F" == "fraction" ]] && continue
  for MODE in $MODES; do
    case "$MODE" in
      fixed) ELASTIC=false ;;
      elastic) ELASTIC=true ;;
      *) echo "Unknown mode: $MODE"; exit 2 ;;
    esac

    TAG="f${F}_c${CAP}_${MODE}"
    OUT="$RESULTS/${TAG}.csv"
    echo "[run] fraction=$F capacity=$CAP mode=$MODE"

    cat > "$APP_CONF" <<EOF
caffeine {
  simulator {
    source = "files"
    files {
      paths = ["$TRACE"]
      format = "adapt-size"
    }
    tiny-lfu {
      count-min {
        lazy = true
      }
    }
    sized-window-tiny-lfu {
      scaled = false
      bump = true
      prune = true
      elastic-buffer = $ELASTIC
    }
    window-tiny-lfu {
      percent-main = [0.99]
      percent-main-protected = 0.80
    }
    maximum-size = $CAP
    policies = ["sketch.SumSizedWindowTinyLfu"]
    admission = ["Always"]
    report {
      format = "csv"
      output = "$OUT"
      sort-by = "policy"
      ascending = true
    }
  }
}
EOF

    (cd "$SRC" && ./gradlew simulator:run -q </dev/null)

    printf '{"fraction": %s, "capacity_bytes": %s, "mode": "%s", "csv": "%s"}\n' \
      "$F" "$CAP" "$MODE" "$(basename "$OUT")" > "$RESULTS/${TAG}.json"
  done
done < "$CAP_META"

echo
echo "Sweep complete."
echo "Analyze with: python3 \"$ROOT/analyze.py\" \"$RESULTS\""
