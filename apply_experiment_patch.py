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

# Elasticity changes physical byte placement only. Window turnover, object-size
# eligibility, and TinyLFU/AV admission are kept at their historical semantics.
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

# Candidate production and admission triggering use the historical nominal Main
# boundary. Thus borrowable global slack never lets a candidate bypass AV.
replace_once(
    sized,
    '''  private void evict() {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n  }\n''',
    '''  private void evict() {\n    final Node headCandidates = new Node();\n    collectCandidates(headCandidates);\n    while (headCandidates.prev != headCandidates) {\n      Node candidate = headCandidates.prev;\n      candidate.remove();\n      if (candidateExceedsNominalMain(candidate)) {\n        coreEviction(candidate);\n      } else {\n        admit(candidate);\n      }\n    }\n\n    if (elasticBuffer) {\n      // Window keeps its historical reservation. If Main had borrowed Window\n      // slack and a later Window insertion reclaims it, Main yields only the\n      // bytes physically required to restore the single global M-byte cap.\n      while (sizeData > maximumSize) {\n        checkState((sizeData - sizeWindow) > 0);\n        victimsCount++;\n        evictNode(getVictim());\n      }\n    }\n  }\n''',
)

# The base policy still compares against the historical victim whenever nominal
# Main capacity says admission is required. After a win, elastic mode may avoid
# the physical eviction if Window slack can hold both objects.
replace_once(
    sized,
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while ((sizeData + candidate.weight - sizeWindow) > maxMain) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n    victimsCount++;\n    if (compare(sketch.frequency(candidate.key), candidate.weight, sketch.frequency(victim.key), victim.weight)) {\n      victimsCount--;\n      while (candidateExceedsPhysicalCapacity(candidate)) {\n        Node evict = getVictim();\n        victimsCount++;\n        evictNode(evict);\n      }\n      admit(candidate);\n    } else {\n''',
)

# Keep the historical Window rule exactly: whenever it exceeds its reservation,
# move LRU entries toward Main until it is back at or below maxWindow.
replace_once(
    sized,
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
    '''  private void collectCandidates(final Node headCandidates) {\n    while (sizeWindow > maxWindow) {\n      Node candidate = headWindow.next;\n      candidate.status = Status.PROBATION;\n      sizeWindow -= candidate.weight;\n      sizeData -= candidate.weight;\n      candidate.remove();\n      candidate.appendToTail(headCandidates);\n    }\n  }\n\n  /** Historical logical admission boundary: the nominal Main reservation. */\n  protected boolean candidateExceedsNominalMain(Node candidate) {\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Historical number of victim bytes AV must evaluate for this candidate. */\n  protected long logicalBytesNeededForCandidate(Node candidate) {\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n\n  /** Physical placement boundary after admission has already been decided. */\n  protected boolean candidateExceedsPhysicalCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return candidateExceedsNominalMain(candidate);\n  }\n\n  /** Physical victim bytes actually required after the candidate wins AV. */\n  protected long physicalBytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return logicalBytesNeededForCandidate(candidate);\n  }\n\n  private void sampleOccupancy() {\n    long mainSize = sizeData - sizeWindow;\n    occupancySamples++;\n    totalOccupancySum += sizeData;\n    windowOccupancySum += sizeWindow;\n    mainOccupancySum += mainSize;\n\n    long windowBorrow = Math.max(0L, sizeWindow - maxWindow);\n    long mainBorrow = Math.max(0L, mainSize - maxMain);\n    if (windowBorrow > 0) {\n      windowBorrowSamples++;\n      maxWindowBorrowBytes = Math.max(maxWindowBorrowBytes, windowBorrow);\n    }\n    if (mainBorrow > 0) {\n      mainBorrowSamples++;\n      maxMainBorrowBytes = Math.max(maxMainBorrowBytes, mainBorrow);\n    }\n  }\n  \n  protected Node getVictim() {\n''',
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

# AV stays lambda=1 and evaluates exactly the historical logical victim set,
# based on overflow beyond nominal Main. Only after the candidate wins do we
# ask how many of those victim bytes must physically leave under the shared M.
replace_once(
    sum_sized,
    '''    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "") \n        + "SumWindowTinyLfu (%.0f%%)", 100 * (1.0d - percentMain));\n''',
    '''    String name = String.format("sketch.sized." + (scaled ? "Scaled" : "")\n        + (elasticBuffer ? "Elastic" : "")\n        + "SumWindowTinyLfu (%.0f%%)", 100 * (1.0d - percentMain));\n''',
)

replace_once(
    sum_sized,
    '''    long sizeNeeded = (sizeData + candidate.weight - sizeWindow) - maxMain;\n    int victimsSize = 0;\n    int victimsNum = 0;\n    int victimsFreq = 0;\n    Node victim = headProbation;\n    while (victimsSize < sizeNeeded) {\n      if (victim.next != headProbation) {\n        victim = victim.next;\n      } else {\n        victim = headProtected.next;\n      }\n      victimsSize += victim.weight;\n      victimsNum++;\n      victimsFreq += sketch.frequency(victim.key);\n      if (prune && victimsFreq > candidateFreq) {\n        break;\n      }\n    }\n    victimsCount += victimsNum;\n    if (!compare(candidateFreq, candidate.weight, victimsFreq, victimsSize)) {\n       reject(candidate);\n       if (bump) {\n         for (int i = 0; i < victimsNum; i++) {\n           promote(getVictim());\n         }\n       }\n    } else {\n      for (int i = 0; i < victimsNum; i++) {\n        Node evict = getVictim();\n        evictNode(evict);\n      }\n      admit(candidate);\n    }    \n''',
    '''    long logicalSizeNeeded = logicalBytesNeededForCandidate(candidate);\n    int victimsSize = 0;\n    int victimsNum = 0;\n    int victimsFreq = 0;\n    Node victim = headProbation;\n    while (victimsSize < logicalSizeNeeded) {\n      if (victim.next != headProbation) {\n        victim = victim.next;\n      } else {\n        victim = headProtected.next;\n      }\n      victimsSize += victim.weight;\n      victimsNum++;\n      victimsFreq += sketch.frequency(victim.key);\n      if (prune && victimsFreq > candidateFreq) {\n        break;\n      }\n    }\n    victimsCount += victimsNum;\n    if (!compare(candidateFreq, candidate.weight, victimsFreq, victimsSize)) {\n       reject(candidate);\n       if (bump) {\n         for (int i = 0; i < victimsNum; i++) {\n           promote(getVictim());\n         }\n       }\n    } else {\n      long physicalSizeNeeded = physicalBytesNeededForCandidate(candidate);\n      long reclaimed = 0L;\n      while (reclaimed < physicalSizeNeeded) {\n        Node evict = getVictim();\n        reclaimed += evict.weight;\n        evictNode(evict);\n      }\n      admit(candidate);\n    }    \n''',
)

replace_once(
    reference,
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n  }\n''',
    '''  sized-window-tiny-lfu {\n    scaled = false\n    bump = false\n    prune = true\n    elastic-buffer = false\n  }\n''',
)

print("Applied simulator compatibility fixes and admission-preserving elastic sharing successfully.")
