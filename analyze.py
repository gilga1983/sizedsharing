#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

results = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []


def read_occupancy_stats(path: Path):
    stats = {}
    if not path.exists():
        return stats
    for line in path.read_text(errors="replace").splitlines():
        marker = line.find("ELASTIC_STATS")
        if marker < 0:
            continue
        payload = line[marker:].split()[1:]
        for item in payload:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            try:
                stats[key] = float(value)
            except ValueError:
                pass
    return stats


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
    occupancy = read_occupancy_stats(results / meta.get("log", ""))
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
        "avg_total_bytes": occupancy.get("avg_total_bytes", float("nan")),
        "avg_utilization": occupancy.get("avg_utilization", float("nan")),
        "avg_window_bytes": occupancy.get("avg_window_bytes", float("nan")),
        "avg_main_bytes": occupancy.get("avg_main_bytes", float("nan")),
        "avg_slack_bytes": occupancy.get("avg_slack_bytes", float("nan")),
        "window_borrow_fraction": occupancy.get("window_borrow_fraction", float("nan")),
        "main_borrow_fraction": occupancy.get("main_borrow_fraction", float("nan")),
        "max_window_borrow_bytes": occupancy.get("max_window_borrow_bytes", float("nan")),
        "max_main_borrow_bytes": occupancy.get("max_main_borrow_bytes", float("nan")),
    })

if not rows:
    raise SystemExit(f"No completed runs found under {results}")

df = pd.DataFrame(rows).sort_values(["capacity_bytes", "mode"])
df.to_csv(results / "all_results.csv", index=False)

metrics = [
    "hit_rate", "weighted_hit_rate", "evictions", "admit_rate", "runtime_ms",
    "avg_total_bytes", "avg_utilization", "avg_window_bytes", "avg_main_bytes",
    "avg_slack_bytes", "window_borrow_fraction", "main_borrow_fraction",
    "max_window_borrow_bytes", "max_main_borrow_bytes",
]

fixed = df[df["mode"] == "fixed"][["capacity_fraction", "capacity_bytes"] + metrics].copy()
fixed = fixed.rename(columns={m: f"fixed_{m}" for m in metrics})
elastic = df[df["mode"] == "elastic"][["capacity_fraction", "capacity_bytes"] + metrics].copy()
elastic = elastic.rename(columns={m: f"elastic_{m}" for m in metrics})
comparison = fixed.merge(elastic, on=["capacity_fraction", "capacity_bytes"], how="inner")
comparison["hit_gain_pp"] = comparison["elastic_hit_rate"] - comparison["fixed_hit_rate"]
comparison["weighted_hit_gain_pp"] = (
    comparison["elastic_weighted_hit_rate"] - comparison["fixed_weighted_hit_rate"]
)
comparison["utilization_gain_pp"] = 100 * (
    comparison["elastic_avg_utilization"] - comparison["fixed_avg_utilization"]
)
comparison["slack_reduction_bytes"] = (
    comparison["fixed_avg_slack_bytes"] - comparison["elastic_avg_slack_bytes"]
)
comparison.to_csv(results / "elastic_vs_fixed.csv", index=False)

print("\nElastic buffer versus fixed 1%/99% partition:")
print(comparison[[
    "capacity_fraction", "capacity_bytes",
    "fixed_hit_rate", "elastic_hit_rate", "hit_gain_pp",
    "fixed_weighted_hit_rate", "elastic_weighted_hit_rate", "weighted_hit_gain_pp",
    "fixed_avg_utilization", "elastic_avg_utilization", "utilization_gain_pp",
    "fixed_avg_slack_bytes", "elastic_avg_slack_bytes", "slack_reduction_bytes",
    "elastic_window_borrow_fraction", "elastic_main_borrow_fraction",
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

fig, ax = plt.subplots()
ax.plot(comparison["capacity_fraction"] * 100, comparison["utilization_gain_pp"], marker="o")
ax.axhline(0.0, linestyle="--")
ax.set_xlabel("Cache capacity (% of unique-byte footprint)")
ax.set_ylabel("Gain in average byte utilization (percentage points)")
ax.set_title("Elastic sharing: recovered stranded capacity")
fig.tight_layout()
fig.savefig(results / "elastic_utilization_gain.png", dpi=180)
plt.close(fig)

print(f"\nWrote results and plots to: {results.resolve()}")
