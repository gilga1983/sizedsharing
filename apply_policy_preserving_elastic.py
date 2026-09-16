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

# Elastic sharing is a physical-placement optimization, not a new admission
# policy. A detached Window candidate must face the same nominal Main-capacity
# admission test as historical AV. Only after AV accepts it may shared slack
# reduce the number of victims that are physically removed.
replace_once(
    sized,
    "      if (candidateExceedsCapacity(candidate)) {\n",
    "      if (candidateNeedsAdmission(candidate)) {\n",
)

replace_once(
    sized,
    '''  protected void coreEviction(Node candidate) {\n    long bytesNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && bytesNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    Node victim = getVictim();\n''',
    '''  protected void coreEviction(Node candidate) {\n    Node victim = getVictim();\n''',
)

replace_once(
    sized,
    "      while (candidateExceedsCapacity(candidate)) {\n",
    "      while (physicalCandidateExceedsCapacity(candidate)) {\n",
)

replace_once(
    sized,
    '''  /** True if admitting this detached Window candidate would exceed its capacity. */\n  protected boolean candidateExceedsCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Bytes that must be reclaimed before this detached candidate can be admitted. */\n  protected long bytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n''',
    '''  /** Historical logical admission boundary: the nominal Main reservation. */\n  protected boolean candidateNeedsAdmission(Node candidate) {\n    return (sizeData + candidate.weight - sizeWindow) > maxMain;\n  }\n\n  /** Physical placement boundary after the logical admission decision. */\n  protected boolean physicalCandidateExceedsCapacity(Node candidate) {\n    if (elasticBuffer) {\n      return (sizeData + candidate.weight) > maximumSize;\n    }\n    return candidateNeedsAdmission(candidate);\n  }\n\n  /** Physical bytes that really must be reclaimed after AV accepts a candidate. */\n  protected long physicalBytesNeededForCandidate(Node candidate) {\n    if (elasticBuffer) {\n      return Math.max(0L, (sizeData + candidate.weight) - maximumSize);\n    }\n    return Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n  }\n''',
)

# AV's comparison set remains exactly the historical one: enough nominal Main
# victims to fit the candidate under the 99% reservation. Shared slack is never
# allowed to make the candidate face an easier frequency test.
replace_once(
    sum_sized,
    '''    long sizeNeeded = bytesNeededForCandidate(candidate);\n    if (elasticBuffer && sizeNeeded > (sizeData - sizeWindow)) {\n      reject(candidate);\n      return;\n    }\n    int victimsSize = 0;\n''',
    '''    long sizeNeeded = Math.max(0L, (sizeData + candidate.weight - sizeWindow) - maxMain);\n    int victimsSize = 0;\n''',
)

# If the candidate wins the historical AV comparison, remove only the victim
# bytes physically required by the global M-byte cap. The remaining logical
# victims stay resident and Main borrows Window's otherwise stranded slack.
replace_once(
    sum_sized,
    '''    } else {\n      for (int i = 0; i < victimsNum; i++) {\n        Node evict = getVictim();\n        evictNode(evict);\n      }\n      admit(candidate);\n    }    \n''',
    '''    } else {\n      long physicalBytesNeeded = physicalBytesNeededForCandidate(candidate);\n      long physicalBytesEvicted = 0L;\n      int physicalVictims = 0;\n      while ((physicalBytesEvicted < physicalBytesNeeded) && (physicalVictims < victimsNum)) {\n        Node evict = getVictim();\n        physicalBytesEvicted += evict.weight;\n        physicalVictims++;\n        evictNode(evict);\n      }\n      if (physicalBytesEvicted < physicalBytesNeeded) {\n        throw new IllegalStateException("Physical eviction exceeded logical AV victim set");\n      }\n      victimsCount -= (victimsNum - physicalVictims);\n      admit(candidate);\n    }    \n''',
)

print("Separated historical AV admission from elastic physical placement successfully.")
