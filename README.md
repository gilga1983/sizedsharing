# SizedSharing

Minimal experiments on **elastic byte sharing inside variable-sized W-TinyLFU**.

The current experiment is cache-only. There is no prefetcher, predictor, residual stream, mapper, controller, or parameter retuning.

We start from the historical sized W-TinyLFU / Aggregated Victims implementation in `ohadeytan/caffeine:arXiv_submission` and keep its admission rule unchanged (`lambda = 1`). The only change is how unused bytes are shared between the Window and Main regions.

The total cache capacity `M` is the only hard byte limit:

```text
bytes(Window) + bytes(Main) <= M
```

The familiar 1% Window / 99% Main split is an **entitlement**, not a pair of rigid byte walls. Variable-size objects can leave packing slack on either side, and the other side may temporarily use those otherwise-stranded bytes.

Borrowed capacity has weak ownership:

- Main may use bytes that the Window cannot currently fill.
- Window may keep one variable-size overshoot while Main has globally free bytes.
- If another miss arrives while Window is already borrowing, Window first returns to its nominal entitlement by pushing old Window entries through the usual candidate path.
- If Window needs bytes currently borrowed by Main, Main yields enough bytes to preserve the single hard global limit `M`.

This is intentionally a packing-friction mechanism, not adaptive Window sizing. The Window is not allowed to grow persistently into unused Main capacity.

## First experiment

Compare exactly two policies:

```text
fixed   = historical 1% Window / 99% Main hard partition
elastic = same policy and same nominal split, but packing slack is shareable
```

Everything else is held constant:

- same total cache bytes;
- same sized W-TinyLFU code;
- same Aggregated Victims admission rule;
- `lambda = 1`;
- same TinyLFU sketch;
- same trace;
- same 1% / 99% nominal split.

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

of the trace's unique-byte footprint.

## Outputs

The analysis produces:

- `results/all_results.csv`
- `results/elastic_vs_fixed.csv`
- `results/elastic_object_hit_gain.png`
- `results/elastic_weighted_hit_gain.png`
- `results/elastic_utilization_gain.png`

Synthetic CI results validate plumbing only. Research conclusions should use real sized-object traces.
