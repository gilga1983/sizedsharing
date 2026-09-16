# SizedSharing

Minimal experiments on **elastic byte sharing inside variable-sized W-TinyLFU**.

The current experiment is cache-only. There is no prefetcher, predictor, residual stream, mapper, controller, or parameter retuning.

We start from the historical sized W-TinyLFU / Aggregated Victims implementation in `ohadeytan/caffeine:arXiv_submission` and keep `lambda = 1`. The only change is how byte slack left by the Window/Main partition is physically used.

The total cache capacity `M` is the only hard physical byte limit:

```text
bytes(Window) + bytes(Main) <= M
```

The Window keeps its historical turnover rule exactly. After an insertion, if the Window exceeds its nominal byte entitlement, it pushes LRU entries through the normal candidate path until:

```text
bytes(Window) <= Window entitlement
```

Variable-size objects can therefore leave unused bytes below the Window entitlement. In the historical fixed policy those bytes are stranded because Main is capped independently. In the elastic policy Main may use them.

The elastic semantics are:

- Window turnover is identical to historical sized W-TinyLFU.
- Window never remains above its nominal entitlement after request processing.
- Candidates evicted from Window try Main against the single global physical limit `M`.
- If Window's variable-size packing left enough global slack for a candidate, Main can place it without evicting a resident object.
- If more bytes are needed, Aggregated Victims compares the candidate against only enough Main victims to free the physically required bytes.
- If Window later needs bytes that Main is using, Main yields enough bytes to preserve the global limit `M`.

This is intentionally a packing-friction mechanism, not adaptive Window sizing.

## Experiment

Compare exactly two policies:

```text
fixed   = historical hard Window/Main byte partition
elastic = same Window policy and nominal split, but Window packing slack is usable by Main
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

This isolates one question: **does eliminating stranded Window packing capacity improve byte utilization and cache performance for variable-sized objects?**

## Constant-size null test

The synthetic generator supports a constant-size mode. The CI null test uses 32 KiB objects and aligns the total cache to 100 objects, so all tested Window fractions are exact whole-object boundaries:

```text
Window = 1%, 5%, 10%, 20%, 40%
```

Under these conditions there is no variable-size packing slack to recover, so fixed and elastic should produce identical cache outcomes. This is used as a semantic regression test for the elastic implementation.

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
