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


for sidecar in sorted(results.glob("f*_w*_c*_*.json")):
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
        "window_fraction": float(meta["window_fraction"]),
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

df = pd.DataFrame(rows).sort_values(["capacity_bytes", "window_fraction", "mode"])
df.to_csv(results / "all_results.csv", index=False)

metrics = [
    "hit_rate", "weighted_hit_rate", "evictions", "admit_rate", "runtime_ms",
    "avg_total_bytes", "avg_utilization", "avg_window_bytes", "avg_main_bytes",
    "avg_slack_bytes", "window_borrow_fraction", "main_borrow_fraction",
    "max_window_borrow_bytes", "max_main_borrow_bytes",
]
keys = ["capacity_fraction", "window_fraction", "capacity_bytes"]
fixed = df[df["mode"] == "fixed"][keys + metrics].copy()
fixed = fixed.rename(columns={m: f"fixed_{m}" for m in metrics})
elastic = df[df["mode"] == "elastic"][keys + metrics].copy()
elastic = elastic.rename(columns={m: f"elastic_{m}" for m in metrics})
comparison = fixed.merge(elastic, on=keys, how="inner")
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

print("\nElastic buffer versus fixed partition:")
print(comparison[[
    "capacity_fraction", "window_fraction", "capacity_bytes",
    "fixed_hit_rate", "elastic_hit_rate", "hit_gain_pp",
    "fixed_weighted_hit_rate", "elastic_weighted_hit_rate", "weighted_hit_gain_pp",
    "fixed_avg_utilization", "elastic_avg_utilization", "utilization_gain_pp",
    "fixed_avg_slack_bytes", "elastic_avg_slack_bytes", "slack_reduction_bytes",
    "elastic_window_borrow_fraction", "elastic_main_borrow_fraction",
]].to_string(index=False))


def plot_vs_window(column, ylabel, filename, title):
    fig, ax = plt.subplots()
    for cap_fraction, group in comparison.groupby("capacity_fraction"):
        group = group.sort_values("window_fraction")
        ax.plot(group["window_fraction"] * 100, group[column], marker="o",
                label=f"cache={100 * cap_fraction:g}% footprint")
    ax.axhline(0.0, linestyle="--")
    ax.set_xlabel("Nominal Window (% of cache)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if comparison["capacity_fraction"].nunique() > 1:
        ax.legend()
    fig.tight_layout()
    fig.savefig(results / filename, dpi=180)
    plt.close(fig)


plot_vs_window(
    "hit_gain_pp",
    "Elastic gain in object hit rate (percentage points)",
    "elastic_object_hit_gain_vs_window.png",
    "Sized W-TinyLFU: elastic gain vs Window fraction",
)
plot_vs_window(
    "weighted_hit_gain_pp",
    "Elastic gain in weighted hit rate (percentage points)",
    "elastic_weighted_hit_gain_vs_window.png",
    "Sized W-TinyLFU: byte-hit gain vs Window fraction",
)
plot_vs_window(
    "utilization_gain_pp",
    "Gain in average byte utilization (percentage points)",
    "elastic_utilization_gain_vs_window.png",
    "Elastic sharing: recovered stranded capacity vs Window fraction",
)

print(f"\nWrote results and plots to: {results.resolve()}")
