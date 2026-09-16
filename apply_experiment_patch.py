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
simulator_build = src / "simulator/build.gradle"
registry = src / "simulator/src/main/java/com/github/benmanes/caffeine/cache/simulator/policy/Registry.java"
collision_policy = src / "simulator/src/main/java/com/github/benmanes/caffeine/cache/simulator/policy/product/CollisionPolicy.java"

# Simulator-only compatibility fixes for the historical branch.
replace_once(
    build,
    "  apply plugin: 'biz.aQute.bnd.builder'\n",
    "  // SizedSharing simulator-only build: obsolete bnd packaging plugin disabled.\n",
)
replace_once(
    simulator_build,
    "  implementation libraries.collision\n",
    "  // SizedSharing simulator-only build: unavailable Collision dependency omitted.\n",
)
replace_once(
    registry,
    "import com.github.benmanes.caffeine.cache.simulator.policy.product.CollisionPolicy;\n",
    "",
)
replace_once(
    registry,
    '    factories.put("product.Collision", CollisionPolicy::policies);\n',
    "",
)
collision_text = collision_policy.read_text()
if "systems.comodal.collision.cache.CollisionBuilder" not in collision_text:
    raise RuntimeError("Historical CollisionPolicy.java did not match expected dependency")
collision_policy.unlink()

# Add a switch for the minimal elastic-buffer experiment. The historical
# 1%/99% split remains the nominal ownership, but in elastic mode only the
# global cache byte limit is hard. Window and Main may borrow unused bytes
# from one another.
replace_once(
    sized,
    '''  protected final boolean bump;\n  protected final boolean prune;  \n''',
    '''  protected final boolean bump;\n  protected final boolean prune;\n  protected final boolean elasticBuffer;  \n''',
)

replace_once(
    sized,
    '''    this.bump = settings.bump();\n    this.prune = settings.prune();\n    this.maxMain = (long) (settings.maximumSizeLong() * percentMain);\n''',
    '''    this.bump = settings.bump();\n    this.prune = settings.prune();\n    this.elasticBuffer = settings.elasticBuffer();\n    this.maxMain = (long) (settings.maximumSizeLong() * percentMain);\n''',
)

replace_once(
    sized,
    '''    if (weight > (maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
    '''    if (weight > (elasticBuffer ? maximumSize : maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
)

replace_once(
    sized,
    '''      if ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n  }\n''',
    '''      if (candidateExceedsCapacity(candidate)) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n\n    // If Window is at or below its nominal reservation, any remaining\n    // overflow belongs to Main borrowing Window's unused bytes. Reclaim only\n    // enough Main bytes to satisfy the single hard global limit.\n    if (elasticBuffer) {\n      while (sizeData > maximumSize) {\n        checkState((sizeData - sizeWindow) > 0);\n        victimsCount++;\n        evictNode(getVictim());\n      }\n    }\n  }\n''',
)

replace_once(
    sized,
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
    '''  protected void coreEviction(Node candidate) {\n    long bytesNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && bytesNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while (candidateExceedsCapacity(candidate)) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
)

replace_once(
    sized,
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
    '''  private void collectCandidates(final Node headCandidates) {\n    if (elasticBuffer) {\n      // Window may exceed its nominal reservation while Main leaves bytes\n      // unused. It gives bytes back only when the global cache is overfull.\n      while ((sizeData > maximumSize) && (sizeWindow > maxWindow)) {\n        Node candidate = headWindow.next;\n        candidate.status = Status.PROBATION;\n        sizeWindow -= candidate.weight;\n        sizeData -= candidate.weight;\n        candidate.remove();\n        candidate.appendToTail(headCandidates);\n      }\n    } else {\n      while (sizeWindow > maxWindow) {\n        Node candidate = headWindow.next;\n        candidate.status = Status.PROBATION;\n        sizeWindow -= candidate.weight;\n        sizeData -= candidate.weight;\n        candidate.remove();\n        candidate.appendToTail(headCandidates);\n      }\n    }\n  }\n\n  /** True if admitting this detached Window candidate would exceed its capacity. */\n  protected boolean candidateExceedsCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Bytes that must be reclaimed before this detached candidate can be admitted. */\n  protected long bytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n  \n  protected Node getVictim() {\n''',
)

replace_once(
    sized,
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n  }\n}\n''',
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n    public boolean elasticBuffer() {\n      return config().getBoolean("sized-window-tiny-lfu.elastic-buffer");\n    }\n  }\n}\n''',
)

# AV still uses the historical lambda=1 candidate-vs-aggregate-victims rule.
# Only its byte-reclamation target changes from the hard Main partition to the
# global limit when elastic mode is enabled.
replace_once(
    sum_sized,
    '''    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "") \n        + "SumWindowTinyLfu (%.0f%%)", 100 * (1.0d - percentMain));\n''',
    '''    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "")\n        + (elasticBuffer ? "Elastic" : "")\n        + "SumWindowTinyLfu (%.0f%%)", 100 * (1.0d - percentMain));\n''',
)

replace_once(
    sum_sized,
    '''    long sizeNeeded = (sizeData + candidate.weight - sizeWindow) - maxMain;\n    int victimsSize = 0;\n''',
    '''    long sizeNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && sizeNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    int victimsSize = 0;\n''',
)

replace_once(
    reference,
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n  }\n''',
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n    elastic-buffer = false\n  }\n''',
)

print("Applied simulator compatibility fixes and minimal elastic Window/Main sharing successfully.")
