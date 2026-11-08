"""Check engine output at the snapshot_2026-10-08T1200 replay time against its answer key.

Save the answer key as data/history/snapshot_2026-10-08T1200/answer_key.json, then run
from the project root:
    python -m harness.test_snapshot

Exit code is 0 when every reference event passes and no detected event is ongoing
that the key does not list as ongoing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from engine.events import analyze
from engine.loader import load_dataset
from harness.test import check_pump_action, match

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "data" / "history" / "snapshot_2026-10-08T1200"
CACHE = ROOT / "cache"
NOW = 1791460800            # 2026-10-08T12:00:00Z

END_TOL_S = 60 * 60         # resolved pump failure recovery
HTL_TOL_H = 0.25            # hours_to_limit_final
LEVEL_TOL_PCT = 1.0         # level_final_pct
REVENUE_TOL_REL = 0.02      # lost_revenue_per_hour


def snapshot_fields(ref: dict, ev: dict) -> list[str]:
    """Checks that only apply to the state at NOW: open or closed status, the live level,
    hours to shutdown, lost revenue per hour, and the alert ordering."""
    fails = []
    if ref["status"] == "ongoing":
        if ev["status"] != "ongoing":
            fails.append("key says ongoing at 12:00, detected as resolved")
        if ref["category"] == "pump_failure":
            if ref.get("level_final_pct") is not None and ev.get("level_pct") is not None:
                d = ev["level_pct"] - ref["level_final_pct"]
                if abs(d) > LEVEL_TOL_PCT:
                    fails.append(f"level {ev['level_pct']:.1f}% vs key {ref['level_final_pct']}%")
            htl = (ev.get("hours_to_limit") or {}).get("p50")
            if ref.get("hours_to_limit_final") is not None:
                if htl is None:
                    fails.append("no hours to shutdown; key has "
                                 f"{ref['hours_to_limit_final']} h")
                elif abs(htl - ref["hours_to_limit_final"]) > HTL_TOL_H:
                    fails.append(f"hours to shutdown {htl:.2f} vs key "
                                 f"{ref['hours_to_limit_final']:.2f}")
            rev = ev.get("lost_revenue_per_hour")
            if ref.get("lost_revenue_per_hour") is not None:
                if rev is None or abs(rev - ref["lost_revenue_per_hour"]) > \
                        REVENUE_TOL_REL * ref["lost_revenue_per_hour"]:
                    fails.append(f"lost revenue/h {rev} vs key {ref['lost_revenue_per_hour']}")
    else:
        if ev["status"] != "resolved":
            fails.append("key says resolved before 12:00, detected as ongoing")
        elif ref["category"] == "pump_failure" and ref.get("end_unix") and ev.get("end_unix"):
            d = ev["end_unix"] - ref["end_unix"]
            if abs(d) > END_TOL_S:
                fails.append(f"recovery {'late' if d > 0 else 'early'} by {abs(d) / 60:.0f} min")
    return fails


def check_one(ref: dict, ev: dict | None) -> list[str]:
    if ev is None:
        return ["not detected"]
    fails = snapshot_fields(ref, ev)
    if ref["category"] == "pump_failure":
        fails += check_pump_action(ref, ev)
    return fails


def check_order(pairs: list[tuple[int, int]]) -> list[str]:
    """pairs: (key order, our position in alerts). Our alerts must rank them the same way."""
    by_key = [p for _, p in sorted(pairs)]
    by_ours = [p for p in sorted(p for _, p in pairs)]
    if by_key == by_ours:
        return []
    return [f"alert order differs from key: key ranks {[k for k, _ in sorted(pairs, key=lambda x: x[1])]}"]


def main() -> int:
    ds = load_dataset(SNAP, cache_dir=CACHE)
    key = json.loads((SNAP / "answer_key.json").read_text(encoding="utf-8"))
    result = analyze(ds, now=NOW)
    ours = result["events"]
    alert_pos = {id(e): i for i, e in enumerate(result["alerts"])}

    used: set[int] = set()
    passed = 0
    order_pairs = []
    print(f"Checking {len(key)} reference events at {result['now_ts']}\n")
    for ref in key:
        ev = match(ref, ours, used)
        if ev is not None:
            used.add(id(ev))
            if ref.get("order") is not None and id(ev) in alert_pos:
                order_pairs.append((ref["order"], alert_pos[id(ev)]))
        fails = check_one(ref, ev)
        if not fails:
            passed += 1
        status = ref["status"]
        print(f"{'PASS' if not fails else 'FAIL'}  {ref['id']:<10} {ref['category']:<16} "
              f"{ref['facility']:<16} {status:<9} onset {ref['onset']}")
        for f in fails:
            print(f"        - {f}")

    fails = check_order(order_pairs) if len(order_pairs) > 1 else []
    if fails:
        print("\nAlert order:")
        for f in fails:
            print(f"  - {f}")

    extra = [e for e in ours if id(e) not in used]
    extra_ongoing = [e for e in extra if e["status"] == "ongoing"]
    print(f"\nReference events passed: {passed}/{len(key)}")
    if extra:
        print(f"Detected but not in answer key: {len(extra)}")
        for e in extra:
            print(f"  {e['status']:<9} {e['category']:<16} {e['facility_id']:<16} onset {e['onset_ts']}")

    return 0 if passed == len(key) and not extra_ongoing and not fails else 1


if __name__ == "__main__":
    sys.exit(main())