#!/usr/bin/env python3
import argparse
import bisect
import math
import random
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--requests", type=int, default=200000)
parser.add_argument("--objects", type=int, default=20000)
parser.add_argument("--alpha", type=float, default=1.05)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--size-mode", choices=["lognormal", "constant"], default="lognormal")
parser.add_argument("--constant-size", type=int, default=32 * 1024)
args = parser.parse_args()

# Keep the request sequence independent of the size distribution. This makes
# constant-size and variable-size experiments differ only in object sizes.
access_rng = random.Random(args.seed)
size_rng = random.Random(args.seed ^ 0x5EED5EED)

weights = [1.0 / ((i + 1) ** args.alpha) for i in range(args.objects)]
total = sum(weights)
cdf = []
running = 0.0
for w in weights:
    running += w / total
    cdf.append(running)

if args.size_mode == "constant":
    if args.constant_size <= 0:
        raise SystemExit("--constant-size must be positive")
    sizes = [args.constant_size] * args.objects
else:
    sizes = []
    for _ in range(args.objects):
        # Stable per-object sizes spanning roughly KBs to a few MB, with a heavy tail.
        s = int(max(512, min(8 * 1024 * 1024,
                             size_rng.lognormvariate(math.log(32 * 1024), 1.35))))
        sizes.append(s)

out = Path(args.output)
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w") as f:
    for t in range(args.requests):
        u = access_rng.random()
        obj = bisect.bisect_left(cdf, u)
        f.write(f"{t} {obj} {sizes[obj]}\n")

print(
    f"wrote {args.requests} requests, {args.objects} objects, "
    f"size_mode={args.size_mode} -> {out}"
)
