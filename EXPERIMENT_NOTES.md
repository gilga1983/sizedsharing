# Experiment notes

## Scope

This experiment changes one thing only: the hard internal byte partition between the Window and Main regions of historical sized W-TinyLFU becomes elastic.

There is no predictor, prefetcher, mapper, controller, lambda tuning, or window-size adaptation. Aggregated Victims uses its historical admission comparison (`lambda = 1`).

## Historical code point

The cache is `SumSizedWindowTinyLfuPolicy` on `ohadeytan/caffeine:arXiv_submission`.

Historically:

```text
maxWindow = 1% of M
maxMain   = 99% of M
```

and both are hard internal limits.

The elastic variant keeps those values as nominal reservations while enforcing only:

```text
bytes(Window) + bytes(Main) <= M
```

## Borrowing semantics

Window may exceed its nominal byte reservation while Main has unused capacity. Main may exceed its nominal reservation while Window has unused capacity.

No action is taken simply because one region exceeds its nominal reservation. Reclamation happens only when the total cache exceeds `M`.

If total usage exceeds `M` and Window is above its nominal reservation, the oldest Window item enters the existing sized W-TinyLFU / Aggregated Victims candidate path. AV remains unchanged except that the number of bytes that must be reclaimed is computed against the global limit in elastic mode.

If total usage exceeds `M` while Window is at or below its nominal reservation, Main is using borrowed Window bytes, so Main victims are evicted only until the global limit is restored.

Objects larger than the nominal Main partition are rejected in fixed mode as before. In elastic mode an object may use the cache as long as it fits within the total cache capacity `M`.

## Controlled comparison

For every trace and total capacity, compare:

```text
fixed   : historical hard 1% / 99% partition
elastic : same nominal 1% / 99% split with bidirectional borrowing
```

Everything else remains identical.

Primary metrics:

1. object hit rate;
2. weighted / byte hit rate;
3. evictions and admission rate as diagnostics.

## Validation

The `fixed` configuration must reproduce the historical sized W-TinyLFU / AV behavior. Synthetic CI is only a plumbing check. Real conclusions should come from sized-object traces.
