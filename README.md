# SizedSharing

Minimal experiments on **elastic byte sharing inside variable-sized W-TinyLFU**.

The current experiment is cache-only. There is no prefetcher, predictor, residual stream, mapper, controller, or parameter retuning.

We start from the historical sized W-TinyLFU / Aggregated Victims implementation in `ohadeytan/caffeine:arXiv_submission` and keep its admission rule unchanged (`lambda = 1`). The only change is that the Window and Main regions may temporarily borrow each other's unused bytes.

The total cache capacity `M` is the only hard byte limit:

```text
bytes(Window) + bytes(Main) <= M
```

The familiar 1% Window / 99% Main split remains the nominal reservation. In the historical fixed policy, those are hard internal capacity boundaries. In the elastic variant they are soft reservations:

- Window may exceed 1% while Main leaves bytes unused.
- Main may exceed 99% while Window leaves bytes unused.
- Space is reclaimed only when the total cache exceeds `M`.

When the cache is overfull, the side currently borrowing capacity gives bytes back. Window overflow follows the existing sized W-TinyLFU / AV candidate path; Main overflow evicts from Main until the global byte limit is restored.

## First experiment

Compare exactly two policies:

```text
fixed   = historical 1% Window / 99% Main hard partition
elastic = same policy and same nominal split, but unused bytes are shareable
```

Everything else is held constant:

- same total cache bytes;
- same sized W-TinyLFU code;
- same Aggregated Victims admission rule;
- `lambda = 1`;
- same TinyLFU sketch;
- same trace;
- same 1% / 99% nominal split.

This isolates one question: **does eliminating stranded capacity between Window and Main improve a variable-sized cache?**

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

The analysis reports both object hit rate and weighted/byte hit rate and produces:

- `results/all_results.csv`
- `results/elastic_vs_fixed.csv`
- `results/elastic_object_hit_gain.png`
- `results/elastic_weighted_hit_gain.png`

Synthetic CI results validate plumbing only. Research conclusions should use real sized-object traces.
