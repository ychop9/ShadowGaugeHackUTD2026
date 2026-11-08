"""Score the engine against answer_key.json. Harness only: the engine never reads the key.

usage: python -m harness.score <folder> [<folder> ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from engine.detect import detect_all
from engine.events import analyze
from engine.loader import last_ts, load_dataset

# Onset tolerances from the brief. Harness only.
TOL_S = {"pump_failure": 15 * 60, "pipeline_leak": 2 * 3600, "pump_degradation": 4 * 3600}


def load_key(folder: Path) -> list[dict] | None:
    path = folder / "answer_key.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _span(xs: list[float]) -> str:
    return f"min {min(xs):+.2f} max {max(xs):+.2f}" if xs else "n/a"


def score_category(name: str, cat: str, expected: list[dict], found: list) -> bool:
    used: set[int] = set()
    missed, onset_h, end_h, wrong_status = [], [], [], []
    for k in expected:
        hit = next((i for i, d in enumerate(found)
                    if i not in used and d.facility_id == k["facility"]
                    and abs(d.onset - k["onset_unix"]) <= TOL_S[cat]), None)
        if hit is None:
            missed.append(k)
            continue
        used.add(hit)
        d = found[hit]
        onset_h.append((d.onset - k["onset_unix"]) / 3600)
        if (d.end is None) != (k["status"] == "ongoing"):
            wrong_status.append((k, d))
        elif d.end is not None:
            end_h.append((d.end - k["end_unix"]) / 3600)
    false = [d for i, d in enumerate(found) if i not in used]

    print(f"{name}: {cat:<17} matched {len(onset_h)}/{len(expected)}, false {len(false)}, "
          f"wrong status {len(wrong_status)} | onset err h {_span(onset_h)} | end err h {_span(end_h)}")
    for k in missed:
        print(f"    missed {k['id']} {k['facility']} onset {k['onset']}")
    for d in false:
        print(f"    false  {d.facility_id} onset {d.onset} ongoing={d.ongoing}")
    for k, d in wrong_status:
        print(f"    status {k['id']} {k['facility']} key={k['status']} engine end={d.end}")
    return not missed and not false and not wrong_status


def score_plans(name: str, result: dict, key: list[dict]) -> bool:
    """Ongoing pump failures: countdown, alert order and plan cost against the key."""
    ok = True
    pf = [a for a in result["alerts"] if a["category"] == "pump_failure"]
    for rank, a in enumerate(pf, start=1):
        k = next((e for e in key if e["category"] == "pump_failure" and e["status"] == "ongoing"
                  and e["facility"] == a["facility_id"]), None)
        if k is None:
            continue
        ref_cost = re.search(r"~\$([\d,]+)", k["reference_action"])
        ref_cost = float(ref_cost.group(1).replace(",", "")) if ref_cost else 0.0
        htl = a["hours_to_limit"]["p50"] if a["hours_to_limit"] else None
        flag = ""
        if rank != k.get("order") or a["est_cost"] > ref_cost * 1.05 + 1:
            flag, ok = "  <-- check", False
        print(f"    {a['facility_id']:<14} order {rank} (key {k.get('order')})  "
              f"hours_to_limit {htl} (key {k.get('hours_to_limit_final')})  "
              f"cost ${a['est_cost']:,.0f} (key ${ref_cost:,.0f}){flag}")
        print(f"      engine: {a['plan_summary']}")
        print(f"      key   : {k['reference_action']}")
    return ok


def run(folder: Path) -> bool:
    ds = load_dataset(folder)
    found = detect_all(ds, now=last_ts(ds))
    key = load_key(folder)
    if key is None:
        print(f"{folder.name}: no answer key, {len(found)} events found")
        for d in found:
            print(f"    {d.category:<17} {d.facility_id:<14} onset {d.onset} ongoing={d.ongoing}")
        return True
    ok = True
    for cat in TOL_S:
        ok &= score_category(folder.name, cat,
                             [e for e in key if e["category"] == cat],
                             [d for d in found if d.category == cat])
    if any(e["status"] == "ongoing" and e["category"] == "pump_failure" for e in key):
        print(f"{folder.name}: plans for ongoing pump failures")
        ok &= score_plans(folder.name, analyze(ds), key)
    return ok


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    results = [run(Path(f)) for f in argv[1:]]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
