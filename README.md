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

The harness checks out the exact historical `ohadeytan/caffeine:arXiv_submission` implementation and applies a checked source transformation. Every expected historical code fragment must match exactly before the experiment edits it.

## Quick CI smoke test

The GitHub Actions workflow runs a compact deterministic synthetic sized-object trace on every push. This validates the historical checkout, transformation, build, sweep, CSV parsing, and plotting. Synthetic results are for plumbing only, not for research claims.

Locally:

```bash
chmod +x run_sweep.sh
./run_sweep.sh --synthetic --requests 200000
python3 analyze.py results
```

## Real traces

For an existing AdaptSize-format trace:

```bash
./run_sweep.sh --trace /path/to/trace.tr
python3 analyze.py results
```

Trace format:

```text
time object_id size_bytes [optional fields...]
```

The intended research progression is Wiki2018 and the sized-cache traces, followed by IBM005/IBM058 from the Prefix Caching evaluation.

## Outputs

The analysis produces:

- `results/all_results.csv`
- `results/best_by_capacity.csv`
- `results/best_lambda_vs_capacity.png`
- `results/object_hit_heatmap.png`
- `results/gain_over_original.png`

Both object hit rate and weighted/byte hit rate are retained.

## Identity check

Before interpreting real results, compare a patched `lambda=1` run against an unmodified historical AV run at the same trace and capacity. Hits, misses, admissions, and evictions should match exactly.

## Interpretation

A useful signal is not one isolated best point. We want the best `lambda` to differ from 1 across multiple adjacent capacities, produce a material gain over historical AV, and replicate across real traces. If Phase 1 succeeds, Phase 2 sweeps the full surface `U(C, lambda, w)` where `w` is the W-TinyLFU window fraction, followed by an online controller.
