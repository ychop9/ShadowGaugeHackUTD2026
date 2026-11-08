from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from engine.detect import detect_pump_failures
from engine.loader import load_dataset, last_ts

ONSET_TOLERANCE_S = 15 * 60   # pump failures: 15 min
CATEGORY = "pump_failure"     # confirm with --categories


def load_key(folder: Path) -> list[dict] | None:
    """Harness-only read of answer_key.json. Returns None if the folder has no key."""
    path = folder / "answer_key.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is expected to be a list of events")
    return data


def print_categories(key: list[dict]) -> None:
    counts = Counter(e["category"] for e in key)
    for cat, n in counts.most_common():
        print(f"{cat}: {n}")


def check_pump_failures(folder: Path, key: list[dict]) -> int:
    ds = load_dataset(folder)
    expected = [e for e in key if e["category"] == CATEGORY]
    found = detect_pump_failures(ds, now=last_ts(ds))

    used: set[int] = set()
    missed: list[str] = []
    matched = 0

    for k in expected:
        hit = next(
            (i for i, d in enumerate(found)
             if i not in used
             and d.facility_id == k["facility"]
             and abs(d.onset - k["onset_unix"]) <= ONSET_TOLERANCE_S),
            None,
        )
        if hit is None:
            missed.append(k["id"])
        else:
            used.add(hit)
            matched += 1

    false_pos = [d for i, d in enumerate(found) if i not in used]

    print(f"{folder.name}: {CATEGORY} matched {matched}/{len(expected)}, "
          f"missed {len(missed)}, false {len(false_pos)}")
    for m in missed:
        print("  missed:", m)
    for d in false_pos:
        print("  false:", d.facility_id, d.onset)
    return 0 if not missed and not false_pos else 1

from engine.detect import detect_pump_degradation

DEG_ONSET_TOLERANCE_S = 4 * 3600


def check_degradation(folder: Path, key: list[dict]) -> int:
    ds = load_dataset(folder)
    expected = [e for e in key if e["category"] == "pump_degradation"]
    found = detect_pump_degradation(ds, now=last_ts(ds))

    used: set[int] = set()
    missed: list[str] = []
    onset_errors_h: list[float] = []
    matched = 0
    for k in expected:
        hit = next(
            (i for i, d in enumerate(found)
             if i not in used
             and d.facility_id == k["facility"]
             and abs(d.onset - k["onset_unix"]) <= DEG_ONSET_TOLERANCE_S),
            None,
        )
        if hit is None:
            missed.append(k["id"])
        else:
            used.add(hit)
            matched += 1
            onset_errors_h.append((found[hit].onset - k["onset_unix"]) / 3600)
    
    if onset_errors_h:
        mean_abs = sum(abs(x) for x in onset_errors_h) / len(onset_errors_h)
        print(f"  onset error (h, detected minus key): "
              f"min {min(onset_errors_h):+.2f}, max {max(onset_errors_h):+.2f}, "
              f"mean abs {mean_abs:.2f}")

    false_pos = [d for i, d in enumerate(found) if i not in used]
    print(f"{folder.name}: pump_degradation matched {matched}/{len(expected)}, "
          f"missed {len(missed)}, false {len(false_pos)}")
    for m in missed:
        print("  missed:", m)
    for d in false_pos:
        print("  false:", d.facility_id, d.onset)
    return 0 if not missed and not false_pos else 1


from engine.detect import detect_pipeline_leaks

LEAK_ONSET_TOLERANCE_S = 2 * 3600


def check_leaks(folder: Path, key: list[dict]) -> int:
    ds = load_dataset(folder)
    expected = [e for e in key if e["category"] == "pipeline_leak"]
    found = detect_pipeline_leaks(ds, now=last_ts(ds))

    used: set[int] = set()
    missed: list[str] = []
    matched = 0
    onset_errors_h: list[float] = []

    for k in expected:
        hit = next(
            (i for i, d in enumerate(found)
             if i not in used
             and d.facility_id == k["facility"]
             and abs(d.onset - k["onset_unix"]) <= LEAK_ONSET_TOLERANCE_S),
            None,
        )
        if hit is None:
            missed.append(k["id"])
        else:
            used.add(hit)
            matched += 1
            onset_errors_h.append((found[hit].onset - k["onset_unix"]) / 3600)

    false_pos = [d for i, d in enumerate(found) if i not in used]
    print(f"{folder.name}: pipeline_leak matched {matched}/{len(expected)}, "
          f"missed {len(missed)}, false {len(false_pos)}")
    if onset_errors_h:
        mean_abs = sum(abs(x) for x in onset_errors_h) / len(onset_errors_h)
        print(f"  leak onset error (h, detected minus key): "
              f"min {min(onset_errors_h):+.2f}, max {max(onset_errors_h):+.2f}, "
              f"mean abs {mean_abs:.2f}")
    for m in missed:
        print("  missed:", m)
    for d in false_pos:
        print("  false:", d.facility_id, d.onset)
    return 0 if not missed and not false_pos else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m harness.score <folder> [--categories]")
        return 2
    folder = Path(argv[1])
    key = load_key(folder)
    if key is None:
        return run_engine_only(folder)
    if "--categories" in argv:
        print_categories(key)
        return 0
    results = [
        check_pump_failures(folder, key),
        check_degradation(folder, key),
        check_leaks(folder, key),
    ]
    return 0 if all(r == 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))