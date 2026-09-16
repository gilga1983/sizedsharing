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

The elastic semantics are deliberately split into **logical admission** and **physical placement**:

- Window turnover is identical to historical sized W-TinyLFU.
- Window never remains above its nominal entitlement after request processing.
- Object-size eligibility is unchanged from the historical policy.
- A Window candidate is tested against the nominal Main reservation exactly as before. Borrowable Window slack never lets a candidate bypass TinyLFU / Aggregated Victims admission.
- Aggregated Victims constructs the same logical victim set implied by overflow beyond nominal Main and applies the historical `lambda = 1` comparison.
- Only after a candidate wins admission does elastic sharing matter physically.
- If Window packing slack gives enough global space, the winning candidate may enter Main while some logically defeated victims remain resident.
- If physical bytes are still required, only enough of those victims are actually evicted to satisfy the global limit `M`.
- If Window later needs bytes that Main is using, Main yields enough bytes to preserve the global limit `M`.

This is intentionally a packing-friction mechanism, not adaptive Window sizing and not a relaxation of admission control.

## Experiment

Compare exactly two policies:

```text
fixed   = historical hard Window/Main byte partition
elastic = same Window policy and admission rule, but Window packing slack is usable by Main
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

This isolates one question: **does eliminating stranded Window packing capacity improve byte utilization and cache performance for variable-sized objects when admission control is held fixed?**

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
