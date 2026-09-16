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

# Minimal elastic-buffer switch. Window turnover is deliberately identical to
# historical sized W-TinyLFU: after every insertion it drains until
# sizeWindow <= maxWindow. Elasticity acts only on physical Main placement, so
# byte slack left by variable-sized Window packing can be consumed by Main.
replace_once(
    sized,
    '''  protected final boolean bump;\n  protected final boolean prune;  \n''',
    '''  protected final boolean bump;\n  protected final boolean prune;\n  protected final boolean elasticBuffer;  \n''',
)

replace_once(
    sized,
    '''  protected long sizeWindow;\n  private long sizeProtected;\n  protected long sizeData;\n  protected long victimsCount;\n''',
    '''  protected long sizeWindow;\n  private long sizeProtected;\n  protected long sizeData;\n  protected long victimsCount;\n\n  // Measurement only: occupancy and borrowing do not affect policy decisions.\n  private long occupancySamples;\n  private double totalOccupancySum;\n  private double windowOccupancySum;\n  private double mainOccupancySum;\n  private long windowBorrowSamples;\n  private long mainBorrowSamples;\n  private long maxWindowBorrowBytes;\n  private long maxMainBorrowBytes;\n''',
)

replace_once(
    sized,
    '''    this.bump = settings.bump();\n    this.prune = settings.prune();\n    this.maxMain = (long) (settings.maximumSizeLong() * percentMain);\n''',
    '''    this.bump = settings.bump();\n    this.prune = settings.prune();\n    this.elasticBuffer = settings.elasticBuffer();\n    this.maxMain = (long) (settings.maximumSizeLong() * percentMain);\n''',
)

# Sample occupancy after every completed request, once all transfers/evictions
# caused by that request have settled.
replace_once(
    sized,
    '''    } else {\n      throw new IllegalStateException();\n    }\n  }\n\n  /** Adds the entry to the admission window, evicting if necessary. */\n''',
    '''    } else {\n      throw new IllegalStateException();\n    }\n    sampleOccupancy();\n  }\n\n  /** Adds the entry to the admission window, evicting if necessary. */\n''',
)

# An object too large for historical Main may still fit under the single global
# M-byte cap in elastic mode. This is a physical-capacity check only.
replace_once(
    sized,
    '''    if (weight > (maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
    '''    if (weight > (elasticBuffer ? maximumSize : maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
)

# Window candidate production is unchanged. The only difference is that a
# detached candidate tests placement against total M bytes in elastic mode.
replace_once(
    sized,
    '''  private void evict() {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n  }\n''',
    '''  private void evict() {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if (candidateExceedsCapacity(candidate)) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n\n    if (elasticBuffer) {\n      // If Window needs bytes currently borrowed by Main, Main yields until the\n      // single global M-byte capacity is restored.\n      while (sizeData > maximumSize) {\n        checkState((sizeData - sizeWindow) > 0);\n        victimsCount++;\n        evictNode(getVictim());\n      }\n    }\n  }\n''',
)

replace_once(
    sized,
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
    '''  protected void coreEviction(Node candidate) {\n    long bytesNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && bytesNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while (candidateExceedsCapacity(candidate)) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
)

# Keep the historical Window rule exactly: whenever it exceeds its reservation,
# move LRU entries toward Main until it is back at or below maxWindow.
replace_once(
    sized,
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n\n  /** True if admitting this detached Window candidate would exceed capacity. */\n  protected boolean candidateExceedsCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Bytes that really must be reclaimed before this candidate can be placed. */\n  protected long bytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n\n  private void sampleOccupancy() {\n    long mainSize = sizeData - sizeWindow;\n    occupancySamples++;\n    totalOccupancySum += sizeData;\n    windowOccupancySum += sizeWindow;\n    mainOccupancySum += mainSize;\n\n    long windowBorrow = Math.max(0L, sizeWindow - maxWindow);\n    long mainBorrow = Math.max(0L, mainSize - maxMain);\n    if (windowBorrow > 0) {\n      windowBorrowSamples++;\n      maxWindowBorrowBytes = Math.max(maxWindowBorrowBytes, windowBorrow);\n    }\n    if (mainBorrow > 0) {\n      mainBorrowSamples++;\n      maxMainBorrowBytes = Math.max(maxMainBorrowBytes, mainBorrow);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
)

# Report measurement-only occupancy data in a machine-readable line. This is
# intentionally outside PolicyStats so the historical result columns remain
# untouched and fixed-mode identity stays easy to verify.
replace_once(
    sized,
    '''    checkState(sizeData <= maximumSize);\n  }\n\n  enum Status {\n''',
    '''    checkState(sizeData <= maximumSize);\n\n    if (occupancySamples > 0) {\n      double avgTotal = totalOccupancySum / occupancySamples;\n      double avgWindow = windowOccupancySum / occupancySamples;\n      double avgMain = mainOccupancySum / occupancySamples;\n      System.out.println("ELASTIC_STATS"\n          + " samples=" + occupancySamples\n          + " avg_total_bytes=" + avgTotal\n          + " avg_utilization=" + (avgTotal / maximumSize)\n          + " avg_window_bytes=" + avgWindow\n          + " avg_main_bytes=" + avgMain\n          + " avg_slack_bytes=" + (maximumSize - avgTotal)\n          + " window_borrow_fraction=" + ((double) windowBorrowSamples / occupancySamples)\n          + " main_borrow_fraction=" + ((double) mainBorrowSamples / occupancySamples)\n          + " max_window_borrow_bytes=" + maxWindowBorrowBytes\n          + " max_main_borrow_bytes=" + maxMainBorrowBytes);\n    }\n  }\n\n  enum Status {\n''',
)

replace_once(
    sized,
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n  }\n}\n''',
    '''    public boolean prune() {\n      return config().getBoolean("sized-window-tiny-lfu.prune");\n    }\n    public boolean elasticBuffer() {\n      return config().getBoolean("sized-window-tiny-lfu.elastic-buffer");\n    }\n  }\n}\n''',
)

# AV remains lambda=1. The victim bytes required are determined by the physical
# capacity boundary: historical maxMain in fixed mode, shared global M in elastic.
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

print("Applied simulator compatibility fixes and Window-invariant elastic sharing successfully.")
