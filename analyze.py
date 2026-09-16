#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

results = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []

for sidecar in sorted(results.glob("f*_c*_*.json")):
    meta = json.loads(sidecar.read_text())
    csv_path = results / meta["csv"]
    if not csv_path.exists():
        continue
    with csv_path.open(newline="") as f:
        data = list(csv.DictReader(f))
    if not data:
        continue
    r = data[0]
    rows.append({
        "capacity_fraction": float(meta["fraction"]),
        "capacity_bytes": int(meta["capacity_bytes"]),
        "mode": meta["mode"],
        "policy": r.get("Policy", ""),
        "hit_rate": float(r["Hit rate"]),
        "weighted_hit_rate": float(r["Weighted Hit Rate"]),
        "hits": int(r["Hits"]),
        "misses": int(r["Misses"]),
        "requests": int(r["Requests"]),
        "evictions": int(r["Evictions"]),
        "admit_rate": float(r["Admit rate"]),
        "runtime_ms": int(r["Time"]),
    })

if not rows:
    raise SystemExit(f"No completed runs found under {results}")

df = pd.DataFrame(rows).sort_values(["capacity_bytes", "mode"])
df.to_csv(results / "all_results.csv", index=False)

fixed = (
    df[df["mode"] == "fixed"]
    [["capacity_fraction", "capacity_bytes", "hit_rate", "weighted_hit_rate",
      "evictions", "admit_rate", "runtime_ms"]]
    .rename(columns={
        "hit_rate": "fixed_hit_rate",
        "weighted_hit_rate": "fixed_weighted_hit_rate",
        "evictions": "fixed_evictions",
        "admit_rate": "fixed_admit_rate",
        "runtime_ms": "fixed_runtime_ms",
    })
)
elastic = (
    df[df["mode"] == "elastic"]
    [["capacity_fraction", "capacity_bytes", "hit_rate", "weighted_hit_rate",
      "evictions", "admit_rate", "runtime_ms"]]
    .rename(columns={
        "hit_rate": "elastic_hit_rate",
        "weighted_hit_rate": "elastic_weighted_hit_rate",
        "evictions": "elastic_evictions",
        "admit_rate": "elastic_admit_rate",
        "runtime_ms": "elastic_runtime_ms",
    })
)
comparison = fixed.merge(elastic, on=["capacity_fraction", "capacity_bytes"], how="inner")
comparison["hit_gain_pp"] = comparison["elastic_hit_rate"] - comparison["fixed_hit_rate"]
comparison["weighted_hit_gain_pp"] = (
    comparison["elastic_weighted_hit_rate"] - comparison["fixed_weighted_hit_rate"]
)
comparison.to_csv(results / "elastic_vs_fixed.csv", index=False)

print("\nElastic buffer versus fixed 1%/99% partition:")
print(comparison[[
    "capacity_fraction", "capacity_bytes",
    "fixed_hit_rate", "elastic_hit_rate", "hit_gain_pp",
    "fixed_weighted_hit_rate", "elastic_weighted_hit_rate", "weighted_hit_gain_pp",
]].to_string(index=False))

fig, ax = plt.subplots()
ax.plot(comparison["capacity_fraction"] * 100, comparison["hit_gain_pp"], marker="o")
ax.axhline(0.0, linestyle="--")
ax.set_xlabel("Cache capacity (% of unique-byte footprint)")
ax.set_ylabel("Elastic gain in object hit rate (percentage points)")
ax.set_title("Sized W-TinyLFU: elastic vs fixed partition")
fig.tight_layout()
fig.savefig(results / "elastic_object_hit_gain.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots()
ax.plot(comparison["capacity_fraction"] * 100, comparison["weighted_hit_gain_pp"], marker="o")
ax.axhline(0.0, linestyle="--")
ax.set_xlabel("Cache capacity (% of unique-byte footprint)")
ax.set_ylabel("Elastic gain in weighted hit rate (percentage points)")
ax.set_title("Sized W-TinyLFU: byte-hit impact of elastic sharing")
fig.tight_layout()
fig.savefig(results / "elastic_weighted_hit_gain.png", dpi=180)
plt.close(fig)

print(f"\nWrote results and plots to: {results.resolve()}")
