# SizedSharing

Capacity-aware resource sharing experiments for variable-sized caching and predictive buffers.

The first experiment asks a deliberately narrow question: **does the best size-aware W-TinyLFU admission exchange rate depend on cache capacity?**

For Aggregated Victims (AV), the historical admission rule is approximately

```text
freq(candidate) >= sum(freq(victim_i))
```

We introduce one scalar, `lambda`:

```text
freq(candidate) >= lambda * sum(freq(victim_i))
```

`lambda = 1.0` is the original AV rule. We sweep cache capacity and `lambda` while keeping the rest of the policy fixed. If the best `lambda` moves systematically with capacity, that is evidence that resizing a variable-sized cache should include re-optimizing its admission policy instead of merely changing the byte budget.

## Phase 1

We hold the W-TinyLFU window at 1% and sweep:

```text
lambda = 0.25 0.50 0.75 1.00 1.25 1.50 2.00 3.00 4.00
```

Cache capacities default to:

```text
0.5% 1% 2% 5% 10% 20% 40%
```

of the unique-byte footprint of the trace prefix.

The harness patches the exact historical `ohadeytan/caffeine:arXiv_submission` implementation rather than reimplementing AV.

## Run

For a public smoke test using a Wiki2018 prefix:

```bash
chmod +x run_sweep.sh
./run_sweep.sh --download-wiki --requests 1000000
python3 analyze.py results
```

For an existing AdaptSize-format trace:

```bash
./run_sweep.sh --trace /path/to/trace.tr
python3 analyze.py results
```

Trace format:

```text
time object_id size_bytes [optional fields...]
```

## Outputs

The analysis produces:

- `results/all_results.csv`
- `results/best_by_capacity.csv`
- `results/best_lambda_vs_capacity.png`
- `results/object_hit_heatmap.png`
- `results/gain_over_original.png`

Both object hit rate and weighted/byte hit rate are retained.

## Interpretation

A useful signal is not one isolated best point. We want the best `lambda` to differ from 1 across multiple adjacent capacities, produce a material gain over historical AV, and replicate across real traces. If Phase 1 succeeds, Phase 2 sweeps the full surface `U(C, lambda, w)` where `w` is the W-TinyLFU window fraction, followed by an online controller.
