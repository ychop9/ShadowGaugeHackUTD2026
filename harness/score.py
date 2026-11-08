from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from engine.detect import detect_pump_degradation, detect_pump_failures
from engine.leak import detect_pipeline_leaks
from engine.loader import Dataset, last_ts, load_dataset

# Scoring rules from the brief. Harness only: the engine never reads these.
PUMP_FAILURE_TOL_S = 15 * 60
DEG_TOL_S = 4 * 3600
LEAK_TOL_S = 2 * 3600

SECONDS_PER_HOUR = 3600


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
    for cat, n in Counter(e["category"] for e in key).most_common():
        print(f"{cat}: {n}")


def score(folder_name: str, category: str, expected: list[dict], found: list,
          tol_s: int) -> int:
    """Match each key event to at most one detection on the same facility within tol_s.
    Reports matches, misses, false detections, and onset error for matched events."""
    used: set[int] = set()
    missed: list[str] = []
    errors_h: list[float] = []

    for k in expected:
        hit = next(
            (i for i, d in enumerate(found)
             if i not in used
             and d.facility_id == k["facility"]
             and abs(d.onset - k["onset_unix"]) <= tol_s),
            None,
        )
        if hit is None:
            missed.append(k["id"])
        else:
            used.add(hit)
            errors_h.append((found[hit].onset - k["onset_unix"]) / SECONDS_PER_HOUR)

    false_pos = [d for i, d in enumerate(found) if i not in used]
    matched = len(errors_h)

    print(f"{folder_name}: {category} matched {matched}/{len(expected)}, "
          f"missed {len(missed)}, false {len(false_pos)}")
    if errors_h:
        mean_abs = sum(abs(x) for x in errors_h) / len(errors_h)
        print(f"  {category} onset error (h, detected minus key): "
              f"min {min(errors_h):+.2f}, max {max(errors_h):+.2f}, "
              f"mean abs {mean_abs:.2f}")
    for m in missed:
        print("  missed:", m)
    for d in false_pos:
        print("  false:", d.facility_id, d.onset)
    return 0 if not missed and not false_pos else 1


def check_pump_failures(ds: Dataset, folder: Path, key: list[dict]) -> int:
    expected = [e for e in key if e["category"] == "pump_failure"]
    found = detect_pump_failures(ds, now=last_ts(ds))
    return score(folder.name, "pump_failure", expected, found, PUMP_FAILURE_TOL_S)


def check_degradation(ds: Dataset, folder: Path, key: list[dict]) -> int:
    expected = [e for e in key if e["category"] == "pump_degradation"]
    found = detect_pump_degradation(ds, now=last_ts(ds))
    return score(folder.name, "pump_degradation", expected, found, DEG_TOL_S)


def check_leaks(ds: Dataset, folder: Path, key: list[dict]) -> int:
    expected = [e for e in key if e["category"] == "pipeline_leak"]
    found = detect_pipeline_leaks(ds, now=last_ts(ds))
    return score(folder.name, "pipeline_leak", expected, found, LEAK_TOL_S)


def run_engine_only(ds: Dataset, folder: Path) -> int:
    """No answer key: print what the engine finds at the folder's 'now'."""
    now = last_ts(ds)
    print(f"{folder.name}: no answer_key.json, scoring skipped. Engine output at now={now}")

    failures = detect_pump_failures(ds, now=now)
    print(f"\nPump failures ({len(failures)}):")
    for d in failures:
        status = "ongoing" if d.ongoing else "resolved"
        print(f"  {d.facility_id:<16} onset={d.onset} repair_end={d.repair_end} {status}")

    degradation = detect_pump_degradation(ds, now=now)
    print(f"\nPump degradation ({len(degradation)}):")
    for d in degradation:
        status = "ongoing" if d.ongoing else "resolved"
        print(f"  {d.facility_id:<16} onset={d.onset} detected={d.detected} "
              f"drop={d.drop_pct:.2f}% {status}")

    leaks = detect_pipeline_leaks(ds, now=now)
    print(f"\nPipeline leaks ({len(leaks)}):")
    for d in leaks:
        status = "ongoing" if d.ongoing else "resolved"
        print(f"  {d.facility_id:<16} onset={d.onset} last_flagged={d.last_flagged} {status}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m harness.score <folder> [--categories]")
        return 2

    folder = Path(argv[1])
    key = load_key(folder)
    ds = load_dataset(folder)

    if key is None:
        return run_engine_only(ds, folder)
    if "--categories" in argv:
        print_categories(key)
        return 0

    results = [
        check_pump_failures(ds, folder, key),
        check_degradation(ds, folder, key),
        check_leaks(ds, folder, key),
    ]
    return 0 if all(r == 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))