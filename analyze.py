#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

results = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []

for sidecar in sorted(results.glob("f*_c*_l*.json")):
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
        "lambda": float(meta["lambda"]),
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

df = pd.DataFrame(rows).sort_values(["capacity_bytes", "lambda"])
df.to_csv(results / "all_results.csv", index=False)

best_idx = df.groupby("capacity_bytes")["hit_rate"].idxmax()
best = df.loc[best_idx].copy().sort_values("capacity_bytes")

baseline = (
    df[df["lambda"].sub(1.0).abs() < 1e-12]
    [["capacity_bytes", "hit_rate", "weighted_hit_rate"]]
    .rename(columns={
        "hit_rate": "baseline_hit_rate",
        "weighted_hit_rate": "baseline_weighted_hit_rate",
    })
)
best = best.merge(baseline, on="capacity_bytes", how="left")
best["gain_pp"] = best["hit_rate"] - best["baseline_hit_rate"]
best["weighted_gain_pp"] = (
    best["weighted_hit_rate"] - best["baseline_weighted_hit_rate"]
)
best.to_csv(results / "best_by_capacity.csv", index=False)

print("\nBest lambda by capacity (object hit rate):")
show = best[
    ["capacity_fraction", "capacity_bytes", "lambda",
     "hit_rate", "baseline_hit_rate", "gain_pp",
     "weighted_hit_rate", "weighted_gain_pp"]
]
print(show.to_string(index=False))

fig, ax = plt.subplots()
ax.plot(best["capacity_fraction"] * 100, best["lambda"], marker="o")
ax.axhline(1.0, linestyle="--")
ax.set_xlabel("Cache capacity (% of unique-byte footprint)")
ax.set_ylabel("Best admission multiplier lambda")
ax.set_title("Capacity-conditioned AV: best lambda")
fig.tight_layout()
fig.savefig(results / "best_lambda_vs_capacity.png", dpi=180)
plt.close(fig)

pivot = df.pivot(index="lambda", columns="capacity_fraction", values="hit_rate")
fig, ax = plt.subplots()
im = ax.imshow(pivot.values, aspect="auto", origin="lower")
ax.set_xticks(range(len(pivot.columns)))
ax.set_xticklabels([f"{100*x:g}%" for x in pivot.columns])
ax.set_yticks(range(len(pivot.index)))
ax.set_yticklabels([f"{x:g}" for x in pivot.index])
ax.set_xlabel("Cache capacity")
ax.set_ylabel("lambda")
ax.set_title("Object hit rate (%)")
fig.colorbar(im, ax=ax, label="Hit rate (%)")
fig.tight_layout()
fig.savefig(results / "object_hit_heatmap.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots()
ax.plot(best["capacity_fraction"] * 100, best["gain_pp"], marker="o")
ax.axhline(0.0, linestyle="--")
ax.set_xlabel("Cache capacity (% of unique-byte footprint)")
ax.set_ylabel("Gain over lambda=1 (percentage points)")
ax.set_title("Value of capacity-conditioned admission")
fig.tight_layout()
fig.savefig(results / "gain_over_original.png", dpi=180)
plt.close(fig)

print(f"\nWrote results and plots to: {results.resolve()}")
