"""Check engine output against the full_week answer key.

Run from the project root:
    python -m harness.test

Exit code is 0 when every reference event passes and no unexpected pump failure is detected.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from engine.events import analyze
from engine.loader import load_dataset

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "history" / "full_week"
CACHE = ROOT / "cache"

ONSET_TOL_S = {"pump_failure": 30 * 60, "pump_degradation": 3 * 3600, "pipeline_leak": 3 * 3600}
END_TOL_S = 60 * 60        # recovery time (detector is accurate to about +/-30 min)
TRIPS_AT_TOL_S = 15 * 60   # time the tank reaches shutdown with no action
SHUT_AFTER_TOL_MIN = 15    # planned shut-in start
COST_TOL_REL = 0.05
COST_TOL_ABS = 10.0


# ---------------------------------------------------------------- parsing

def parse_reference(action: str) -> dict:
    """Parse an answer-key reference_action such as '1 truck, 2 trips (~$1,810)'."""
    cost_m = re.search(r"~\$([\d,]+)", action)
    out = {
        "none": action.lower().startswith("none"),
        "trucks": 0, "trips": 0, "shut_wells": [], "shut_after_min": None,
        "cost": float(cost_m.group(1).replace(",", "")) if cost_m else None,
    }
    if out["none"]:
        return out
    # Drop the trailing parentheses so '(1 of 2 trucks free...)' is not read as an action.
    head = action.split(" (")[0]
    t = re.search(r"(\d+) trucks?", head)
    p = re.search(r"(\d+) trips?", head)
    out["trucks"] = int(t.group(1)) if t else 0
    out["trips"] = int(p.group(1)) if p else 0
    out["shut_wells"] = re.findall(r"S\d_WELL_\w+", head)
    s = re.search(r"at \+(\d+) min", head)
    out["shut_after_min"] = int(s.group(1)) if s else None
    return out


def parse_ours(rec: dict) -> dict:
    trucks = trips = 0
    shut_wells, shut_after = [], None
    for a in rec["actions"]:
        if a["type"] == "dispatch_truck":
            trucks += a["trucks"]
            trips += a["trucks"] * a["trips_per_truck"]
        elif a["type"] == "shut_in_wells":
            shut_wells = list(a["wells"])
            shut_after = a["start_after_min"]
    return {"trucks": trucks, "trips": trips, "shut_wells": shut_wells,
            "shut_after_min": shut_after, "cost": rec["est_cost"]}


# ---------------------------------------------------------------- matching

def match(ref: dict, ours: list[dict], used: set[int]) -> dict | None:
    """Closest unused detected event with the same category and facility, within the
    category's onset tolerance. Slow problems confirm after a full hour, so they get a wider window."""
    tol = ONSET_TOL_S[ref["category"]]
    cands = [e for e in ours
             if id(e) not in used
             and e["category"] == ref["category"]
             and e["facility_id"] == ref["facility"]
             and abs(e["onset_unix"] - ref["onset_unix"]) <= tol]
    if not cands:
        return None
    return min(cands, key=lambda e: abs(e["onset_unix"] - ref["onset_unix"]))


# ---------------------------------------------------------------- checks

def check_pump_action(ref: dict, ev: dict) -> list[str]:
    rec = ev.get("onset_recommendation")
    if rec is None:
        return ["no onset recommendation produced"]
    want = parse_reference(ref["reference_action"])
    got = parse_ours(rec)
    fails = []

    if want["none"]:
        if got["trucks"] or got["shut_wells"]:
            fails.append(f"reference: no action; ours: {rec['summary']}")
    else:
        if got["trucks"] != want["trucks"] or got["trips"] != want["trips"]:
            fails.append(f"trucks/trips: reference {want['trucks']}/{want['trips']}, "
                         f"ours {got['trucks']}/{got['trips']}")
        if sorted(got["shut_wells"]) != sorted(want["shut_wells"]):
            fails.append(f"shut-in wells: reference {want['shut_wells'] or 'none'}, "
                         f"ours {got['shut_wells'] or 'none'}")
        if (want["shut_after_min"] is not None and got["shut_after_min"] is not None
                and abs(got["shut_after_min"] - want["shut_after_min"]) > SHUT_AFTER_TOL_MIN):
            fails.append(f"shut-in start: reference +{want['shut_after_min']} min, "
                         f"ours +{got['shut_after_min']} min")

    if want["cost"] is not None:
        tol = max(COST_TOL_ABS, COST_TOL_REL * want["cost"])
        if abs(got["cost"] - want["cost"]) > tol:
            fails.append(f"cost: reference ${want['cost']:,.0f}, ours ${got['cost']:,.0f}")

    ours_min = rec["do_nothing_shutdown_after_min"]
    ref_trips = ref.get("trips_at_unix")
    if ref_trips is None:
        if ours_min is not None:
            fails.append(f"reference never trips; ours trips at +{ours_min} min")
    elif ours_min is None:
        fails.append(f"reference trips at {ref['trips_at']}; ours never trips")
    else:
        ours_ts = ev["onset_unix"] + ours_min * 60
        dt = ours_ts - ref_trips
        if abs(dt) > TRIPS_AT_TOL_S:
            fails.append(f"shutdown {'late' if dt > 0 else 'early'} by {abs(dt) / 60:.0f} min")
    return fails


def check_event(ref: dict, ev: dict | None) -> list[str]:
    if ev is None:
        return ["not detected"]
    fails = []
    if ref.get("end_unix") is not None:
        if ev["end_unix"] is None:
            fails.append("recovery not detected (still ongoing)")
        else:
            d = ev["end_unix"] - ref["end_unix"]
            if abs(d) > END_TOL_S:
                fails.append(f"recovery {'late' if d > 0 else 'early'} by {abs(d) / 60:.0f} min")
    if ref["category"] == "pump_failure":
        fails += check_pump_action(ref, ev)
    return fails


# ---------------------------------------------------------------- main

def main() -> int:
    ds = load_dataset(DATA, cache_dir=CACHE)
    key = json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))
    ours = analyze(ds)["events"]

    used: set[int] = set()
    passed = 0
    print(f"Checking {len(key)} reference events from {DATA.name}\n")
    for ref in key:
        ev = match(ref, ours, used)
        if ev is not None:
            used.add(id(ev))
        fails = check_event(ref, ev)
        if not fails:
            passed += 1
        print(f"{'PASS' if not fails else 'FAIL'}  {ref['id']:<10} {ref['category']:<16} "
              f"{ref['facility']:<16} onset {ref['onset']}")
        for f in fails:
            print(f"        - {f}")

    extra = [e for e in ours if id(e) not in used]
    print(f"\nReference events passed: {passed}/{len(key)}")
    if extra:
        print(f"Detected but not in answer key: {len(extra)}")
        for e in extra:
            print(f"  {e['category']:<16} {e['facility_id']:<16} onset {e['onset_ts']}")

    extra_failures = [e for e in extra if e["category"] == "pump_failure"]
    return 0 if passed == len(key) and not extra_failures else 1


if __name__ == "__main__":
    sys.exit(main())