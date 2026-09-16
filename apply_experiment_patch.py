#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1))


src = Path.cwd()
base = src / "simulator/src/main/java/com/github/benmanes/caffeine/cache/simulator/policy/sketch/sized"
sized = base / "SizedWindowTinyLfuPolicy.java"
sum_sized = base / "SumSizedWindowTinyLfuPolicy.java"
reference = src / "simulator/src/main/resources/reference.conf"
build = src / "build.gradle"

# The historical bnd plugin is packaging/OSGi machinery. Its 2019-era plugin
# dependency no longer resolves cleanly on current runners and is not needed to
# compile or execute the simulator. Guard the exact line so an upstream change
# cannot silently alter what this experiment builds.
replace_once(
    build,
    "  apply plugin: 'biz.aQute.bnd.builder'\n",
    "  // SizedSharing simulator-only build: obsolete bnd packaging plugin disabled.\n",
)

replace_once(
    sized,
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n''',
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n    public double admissionMultiplier() {\n      return config().getDouble("sized-window-tiny-lfu.admission-multiplier");\n    }\n''',
)

replace_once(
    sum_sized,
    '''public final class SumSizedWindowTinyLfuPolicy extends SizedWindowTinyLfuPolicy {\n\n''',
    '''public final class SumSizedWindowTinyLfuPolicy extends SizedWindowTinyLfuPolicy {\n  private final double admissionMultiplier;\n\n''',
)

replace_once(
    sum_sized,
    '''    super(percentMain, settings);\n    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "") \n        + "SumWindowTinyLfu (%.0f%%)", 100 * (1.0d - percentMain));\n''',
    '''    super(percentMain, settings);\n    this.admissionMultiplier = settings.admissionMultiplier();\n    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "") \n        + "SumWindowTinyLfu (%.0f%%, lambda=%.2f)",\n        100 * (1.0d - percentMain), admissionMultiplier);\n''',
)

replace_once(
    sum_sized,
    '''      if (prune && victimsFreq > candidateFreq) {\n        break;\n      }\n''',
    '''      if (prune && candidateFreq < (admissionMultiplier * victimsFreq)) {\n        break;\n      }\n''',
)

replace_once(
    sum_sized,
    '''    if (!compare(candidateFreq, candidate.weight, victimsFreq, victimsSize)) {\n''',
    '''    if (!compareAggregate(candidateFreq, candidate.weight, victimsFreq, victimsSize)) {\n''',
)

replace_once(
    sum_sized,
    '''      admit(candidate);\n    }    \n  }\n}\n''',
    '''      admit(candidate);\n    }    \n  }\n\n  /** Applies a tunable exchange rate to the aggregate victim score. */\n  private boolean compareAggregate(int candidateFreq, int candidateWeight,\n      int victimsFreq, int victimsWeight) {\n    if (admissionMultiplier == 1.0d) {\n      return compare(candidateFreq, candidateWeight, victimsFreq, victimsWeight);\n    }\n    if (scaled) {\n      return ((double) candidateFreq * victimsWeight)\n          > (admissionMultiplier * victimsFreq * candidateWeight);\n    }\n    return candidateFreq >= (admissionMultiplier * victimsFreq);\n  }\n}\n''',
)

replace_once(
    reference,
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n  }\n''',
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n    admission-multiplier = 1.0\n  }\n''',
)

print("Applied simulator-only build fix and capacity-conditioned AV source transformation successfully.")
