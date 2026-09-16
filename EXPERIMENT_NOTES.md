# Experiment notes

## Exact historical code point

The AV implementation is:

`simulator/src/main/java/com/github/benmanes/caffeine/cache/simulator/policy/sketch/sized/SumSizedWindowTinyLfuPolicy.java`

It accumulates the frequencies of enough victims to make room for the candidate and then calls the inherited `compare(...)`.

For `scaled=false`, the inherited rule is:

```text
candidateFreq >= victimFreq
```

where `victimFreq` is the aggregate victim frequency supplied by AV.

The historical configuration exposes:

```text
sized-window-tiny-lfu {
  scaled = false
  bump = false
  prune = true
}
```

and standard W-TinyLFU uses:

```text
window-tiny-lfu {
  percent-main = [0.99]
  percent-main-protected = 0.80
}
```

The old experiment-specific `application.conf` set `bump=true`, so Phase 1 preserves that setup.

## Why pruning must also change

The original AV code can stop gathering victims early when:

```text
victimsFreq > candidateFreq
```

because for `lambda=1` that already proves the candidate will be rejected.

If the admission threshold becomes

```text
candidateFreq >= lambda * victimsFreq
```

the corresponding safe stopping condition is

```text
candidateFreq < lambda * victimsFreq
```

Changing the final admission test without changing pruning would bias the experiment, especially for `lambda < 1`.

## Phase 1 intentionally avoids adaptive window sizing

Window adaptation is established prior work and would make attribution muddy. We first ask whether AV's exchange rate has a capacity-dependent optimum with the same 1% window everywhere.

If yes, Phase 2 can sweep:

```text
U(C, lambda, w)
```

where `w` is the W-TinyLFU window fraction.

## Identity check

Before interpreting results, compare one `lambda=1` patched run against an unpatched historical checkout at the same trace and capacity. Hits, misses, admissions, and evictions should match exactly.

## Recommended progression

1. 1M Wiki2018 requests: smoke test and code validation.
2. 5M to 10M Wiki2018: check whether the surface stabilizes.
3. Full Wiki2018: real result.
4. IBM005 and IBM058: especially interesting because previous experiments exposed non-monotonic behavior as cache capacity increased.
5. Original size-aware paper traces if still available: direct continuity with the earlier result.

## Success criterion

Do not treat one noisy optimum as evidence. The signal becomes interesting if:

1. the best `lambda` differs from 1 at multiple adjacent capacities;
2. the direction is systematic with capacity or workload scarcity;
3. the gain over `lambda=1` is material;
4. the effect appears on multiple real traces;
5. object-hit improvement does not merely trade away byte efficiency.
