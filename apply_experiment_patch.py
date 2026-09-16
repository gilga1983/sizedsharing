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

# Minimal elastic-buffer switch. The historical Window/Main policy remains the
# same; only byte ownership becomes soft. Borrowing is deliberately bounded:
# Window may use one variable-size overshoot while Main has slack, but if Window
# is already borrowing when the next miss arrives it must return to its nominal
# byte entitlement before keeping the new insertion.
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

replace_once(
    sized,
    '''  private void onMiss(long key, int weight) {\n    if (sizeData >= (maximumSize >>> 1)) {\n''',
    '''  private void onMiss(long key, int weight) {\n    long windowSizeBeforeMiss = sizeWindow;\n    if (sizeData >= (maximumSize >>> 1)) {\n''',
)

replace_once(
    sized,
    '''    if (weight > (maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
    '''    if (weight > (elasticBuffer ? maximumSize : maxMain)) {\n      policyStats.recordRejection();\n      return;\n    }\n''',
)

replace_once(
    sized,
    '''    sizeWindow += weight;\n    sizeData += weight;\n    evict();\n  }\n''',
    '''    sizeWindow += weight;\n    sizeData += weight;\n    evict(windowSizeBeforeMiss);\n  }\n''',
)

# Fixed mode is byte-for-byte the historical behavior. Elastic mode keeps the
# same candidate path, but tests Main admission against the global M-byte cap.
# Thus Main can consume Window packing slack. If a new Window insertion needs
# bytes that Main had borrowed, Main gives those bytes back.
replace_once(
    sized,
    '''  private void evict() {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n  }\n''',
    '''  private void evict(long windowSizeBeforeMiss) {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates, windowSizeBeforeMiss);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if (candidateExceedsCapacity(candidate)) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n\n    if (elasticBuffer) {\n      // Window is entitled to its current bounded occupancy. If total bytes\n      // still exceed M, Main was borrowing those bytes and yields them now.\n      while (sizeData > maximumSize) {\n        checkState((sizeData - sizeWindow) > 0);\n        victimsCount++;\n        evictNode(getVictim());\n      }\n    }\n  }\n''',
)

replace_once(
    sized,
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
    '''  protected void coreEviction(Node candidate) {\n    long bytesNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && bytesNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while (candidateExceedsCapacity(candidate)) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
)

# A Window at/below its nominal allocation may keep one overshoot when global
# capacity is available. That borrowed occupancy is weak ownership: if another
# miss arrives while Window is borrowing, it transfers enough LRU bytes toward
# Main to return to its nominal reservation. It may borrow again only after it
# has first surrendered the previous borrow.
replace_once(
    sized,
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
    '''  private void collectCandidates(final Node headCandidates, long windowSizeBeforeMiss) {\n    if (!elasticBuffer) {\n      while (sizeWindow > maxWindow) {\n        detachWindowCandidate(headCandidates);\n      }\n      return;\n    }\n\n    boolean wasBorrowing = windowSizeBeforeMiss > maxWindow;\n    if (wasBorrowing) {\n      while (sizeWindow > maxWindow) {\n        detachWindowCandidate(headCandidates);\n      }\n    } else if (sizeData > maximumSize) {\n      // There is no free global capacity to finance a fresh Window overshoot.\n      while (sizeWindow > maxWindow) {\n        detachWindowCandidate(headCandidates);\n      }\n    }\n    // Otherwise this request may temporarily keep one variable-size overshoot.\n  }\n\n  private void detachWindowCandidate(final Node headCandidates) {\n    Node candidate = headWindow.next;\n    candidate.status = Status.PROBATION;\n    sizeWindow -= candidate.weight;\n    sizeData -= candidate.weight;\n    candidate.remove();\n    candidate.appendToTail(headCandidates);\n  }\n\n  /** True if admitting this detached Window candidate would exceed its capacity. */\n  protected boolean candidateExceedsCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Bytes that must be reclaimed before this detached candidate can be admitted. */\n  protected long bytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n\n  private void sampleOccupancy() {\n    long mainSize = sizeData - sizeWindow;\n    occupancySamples++;\n    totalOccupancySum += sizeData;\n    windowOccupancySum += sizeWindow;\n    mainOccupancySum += mainSize;\n\n    long windowBorrow = Math.max(0L, sizeWindow - maxWindow);\n    long mainBorrow = Math.max(0L, mainSize - maxMain);\n    if (windowBorrow > 0) {\n      windowBorrowSamples++;\n      maxWindowBorrowBytes = Math.max(maxWindowBorrowBytes, windowBorrow);\n    }\n    if (mainBorrow > 0) {\n      mainBorrowSamples++;\n      maxMainBorrowBytes = Math.max(maxMainBorrowBytes, mainBorrow);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
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

# AV stays lambda=1. Only the number of victim bytes required to place a
# candidate changes: fixed mode uses maxMain; elastic mode uses the shared M.
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

print("Applied simulator compatibility fixes and reclaim-on-next-miss elastic sharing successfully.")
