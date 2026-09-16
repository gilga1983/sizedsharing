# SizedSharing

Minimal experiments on **elastic byte sharing inside variable-sized W-TinyLFU**.

The current experiment is cache-only. There is no prefetcher, predictor, residual stream, mapper, controller, or parameter retuning.

We start from the historical sized W-TinyLFU / Aggregated Victims implementation in `ohadeytan/caffeine:arXiv_submission` and keep `lambda = 1`. The only change is how unused bytes are shared between the Window and Main regions.

The total cache capacity `M` is the only hard physical byte limit:

```text
bytes(Window) + bytes(Main) <= M
```

The nominal Window/Main split is an **entitlement**, not a pair of rigid byte walls. Variable-size objects can leave packing slack on either side, and the other side may use those otherwise-stranded bytes.

Borrowed capacity has weak ownership:

- Main may use bytes that the Window cannot currently fill.
- Window may keep one variable-size overshoot while Main has globally free bytes.
- If another miss arrives while Window is already borrowing, Window first returns to or below its nominal entitlement by pushing old Window entries through the usual candidate path.
- When Window evicts candidates, it drains until it is at or below its nominal byte entitlement.
- Those candidates then try Main against the global physical limit `M`.
- If Window's variable-size eviction left enough global slack for a candidate, Main admits it without evicting a resident object.
- If more bytes are needed, Aggregated Victims compares the candidate against only enough Main victims to free the physically required bytes.

This is intentionally a packing-friction mechanism, not adaptive Window sizing. The Window is not allowed to grow persistently into unused Main capacity.

## Experiment

Compare exactly two policies:

```text
fixed   = historical hard Window/Main byte partition
elastic = same nominal split, but packing slack is shareable
```

Everything else is held constant:

- same total cache bytes;
- same sized W-TinyLFU code;
- same Aggregated Victims rule with `lambda = 1`;
- same TinyLFU sketch;
- same trace;
- same nominal Window/Main split.

The harness can sweep the nominal Window fraction using `WINDOW_FRACTIONS`. For example:

```bash
WINDOW_FRACTIONS="0.01 0.05 0.10 0.20 0.40" \
CAPACITY_FRACTIONS="0.05" \
./run_sweep.sh --synthetic --requests 200000
```

This isolates one question: **does eliminating stranded capacity between Window and Main improve byte utilization and cache performance for variable-sized objects?**

## Measurements

In addition to object hit rate and weighted/byte hit rate, the harness records occupancy-only instrumentation:

- average total byte utilization;
- average slack bytes;
- average Window and Main occupancy;
- fraction of requests where Window or Main is borrowing;
- maximum borrowed bytes on either side.

These counters do not affect policy decisions.

## Harness

The harness checks out the exact historical branch and applies a checked source transformation. It also removes two obsolete build-time dependencies that are unrelated to the simulator policy: the old bnd packaging plugin and the unavailable Collision product-cache dependency.

Run a synthetic smoke test:

```bash
chmod +x run_sweep.sh
./run_sweep.sh --synthetic --requests 200000
python3 analyze.py results
```

Run an AdaptSize-format trace:

```bash
./run_sweep.sh --trace /path/to/trace.tr
python3 analyze.py results
```

Trace format:

```text
time object_id size_bytes [optional fields...]
```

The default capacity sweep is:

```text
0.5% 1% 2% 5% 10% 20% 40%
```

of the trace's unique-byte footprint. The default Window remains 1% unless `WINDOW_FRACTIONS` is overridden.

## Outputs

The analysis produces:

- `results/all_results.csv`
- `results/elastic_vs_fixed.csv`
- `results/elastic_object_hit_gain_vs_window.png`
- `results/elastic_weighted_hit_gain_vs_window.png`
- `results/elastic_utilization_gain_vs_window.png`

Synthetic CI results validate plumbing only. Research conclusions should use real sized-object traces.
