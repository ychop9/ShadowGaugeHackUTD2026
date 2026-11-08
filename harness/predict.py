"""Write the engine's predictions in the same format as answer_key.json.

Run from the project root:
    python -m harness.predict full        -> harness/output.txt
    python -m harness.predict snapshot    -> harness/output.txt

Each detected event takes the id of the reference event it matches, so the two files line up.
Unmatched detections get an id starting with UNMATCHED-.
Each run overwrites harness/output.txt, so run one mode at a time.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from engine.events import analyze
from engine.loader import load_dataset

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
FULL_WEEK = ROOT / "data" / "history" / "full_week"
SNAPSHOT = ROOT / "data" / "history" / "snapshot_2026-10-08T1200"
SNAPSHOT_NOW = 1791460800          # 2026-10-08T12:00:00Z
OUTPUT = ROOT / "harness" / "output.txt"

ONSET_TOL_S = {"pump_failure": 30 * 60, "pump_degradation": 3 * 3600, "pipeline_leak": 3 * 3600}


def iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def match(ref: dict, ours: list[dict], used: set[int]) -> dict | None:
    """Closest unused detection with the same category and facility, within onset tolerance."""
    tol = ONSET_TOL_S[ref["category"]]
    cands = [e for e in ours
             if id(e) not in used
             and e["category"] == ref["category"]
             and e["facility_id"] == ref["facility"]
             and abs(e["onset_unix"] - ref["onset_unix"]) <= tol]
    if not cands:
        return None
    return min(cands, key=lambda e: abs(e["onset_unix"] - ref["onset_unix"]))


def action_text(rec: dict) -> str:
    """Render an onset recommendation in the key's style, e.g. '1 truck, 2 trips (~$1,810)'."""
    parts = []
    for a in rec["actions"]:
        if a["type"] == "dispatch_truck":
            t, k = a["trucks"], a["trips_per_truck"]
            parts.append(f"{t} truck{'s' if t > 1 else ''}, {k} trip{'s' if k > 1 else ''}")
        elif a["type"] == "shut_in_wells":
            parts.append(f"shut in {', '.join(a['wells'])} at +{a['start_after_min']} min")
    cost = f"~${rec['est_cost']:,.0f}"
    return " + ".join(parts) + f" ({cost})" if parts else f"none ({cost})"


def base_record(ref_id: str, ev: dict) -> dict:
    return {
        "id": ref_id,
        "system": ev["system_id"],
        "facility": ev["facility_id"],
        "asset": ev["asset_id"],
        "category": ev["category"],
        "onset": ev["onset_ts"],
        "onset_unix": ev["onset_unix"],
        "end": ev["end_ts"],
        "end_unix": ev["end_unix"],
        "status": ev["status"],
    }


def predict(ds, key: list[dict], now: int | None) -> list[dict]:
    result = analyze(ds, now=now) if now is not None else analyze(ds)
    ours = result["events"]
    alert_rank = {id(e): i + 1 for i, e in enumerate(result["alerts"])}

    ref_for: dict[int, str] = {}
    used: set[int] = set()
    for ref in key:
        ev = match(ref, ours, used)
        if ev is not None:
            used.add(id(ev))
            ref_for[id(ev)] = ref["id"]

    records = []
    for ev in ours:
        ref_id = ref_for.get(id(ev), f"UNMATCHED-{ev['event_id']}")
        rec = base_record(ref_id, ev)
        if ev["category"] == "pump_failure":
            onset = ev.get("onset_recommendation")
            if onset is None:
                rec["reference_action"] = "none (no onset recommendation)"
                rec["trips_at"] = rec["trips_at_unix"] = None
            else:
                rec["reference_action"] = action_text(onset)
                m = onset["do_nothing_shutdown_after_min"]
                rec["trips_at_unix"] = None if m is None else ev["onset_unix"] + m * 60
                rec["trips_at"] = iso(rec["trips_at_unix"])
        else:
            rec["reference_action"] = "field_inspection"
        if now is not None and ev["status"] == "ongoing":
            rec["order"] = alert_rank.get(id(ev))
            if ev["category"] == "pump_failure":
                rec["level_final_pct"] = ev.get("level_pct")
                rec["hours_to_limit_final"] = (ev.get("hours_to_limit") or {}).get("p50")
                rec["lost_revenue_per_hour"] = ev.get("lost_revenue_per_hour")
        records.append(rec)

    records.sort(key=lambda r: r["onset_unix"])
    return records


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "full":
        folder, now, label = FULL_WEEK, None, "full_week"
    elif mode == "snapshot":
        folder, now, label = SNAPSHOT, SNAPSHOT_NOW, "snapshot_2026-10-08T1200"
    else:
        print("Usage: python -m harness.predict [full|snapshot]")
        return 2

    key_path = folder / "answer_key.json"
    if not key_path.exists():
        print(f"Missing {key_path}")
        return 2
    key = json.loads(key_path.read_text(encoding="utf-8"))
    ds = load_dataset(folder, cache_dir=CACHE)
    records = predict(ds, key, now)

    out = OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    matched = sum(1 for r in records if not r["id"].startswith("UNMATCHED-"))
    print(f"Wrote {len(records)} predicted events for {label} to {out}")
    print(f"Matched to reference ids: {matched}. Unmatched detections: {len(records) - matched}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())