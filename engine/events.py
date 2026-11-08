"""One call for the whole engine: detect, forecast, plan, and order for the alerts view.

    from engine.events import analyze
    result = analyze(load_dataset("data/history/snapshot_2026-10-08T1200"))

Events use the events.json shape from docs/SPEC.md, plus a few display fields.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .detect import Event, detect_all
from .loader import Dataset, last_ts
from .plan import plan_ongoing_failures


def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analyze(ds: Dataset, now: int | None = None) -> dict:
    """`now` defaults to the last telemetry timestamp; pass an earlier one to time-travel."""
    now = last_ts(ds) if now is None else now
    found = sorted(detect_all(ds, now), key=lambda e: e.onset)
    ongoing_failures = [e for e in found if e.category == "pump_failure" and e.ongoing]
    plans = plan_ongoing_failures(ds, ongoing_failures, now)

    events = []
    for n, ev in enumerate(found, start=1):
        events.append(_to_dict(ev, n, plans.get(ev.facility_id) if ev in ongoing_failures else None))

    alerts = [e for e in events if e["status"] == "ongoing"]
    alerts.sort(key=lambda e: (
        e["category"] != "pump_failure",                              # failures first
        e["hours_to_limit"]["p50"] if e["hours_to_limit"] else float("inf"),
        -(e.get("lost_revenue_per_hour") or 0),                        # tie: costlier first
    ))
    return {"dataset": ds.name, "now_unix": now, "now_ts": _iso(now),
            "alerts": alerts, "events": events}


def _to_dict(ev: Event, n: int, planned) -> dict:
    d = {
        "event_id": f"EV-{n:04d}",
        "system_id": ev.system_id,
        "facility_id": ev.facility_id,
        "asset_id": ev.asset_id,
        "category": ev.category,
        "status": "ongoing" if ev.ongoing else "resolved",
        "onset_ts": _iso(ev.onset),
        "onset_unix": ev.onset,
        "end_ts": _iso(ev.end),
        "end_unix": ev.end,
        "confidence": ev.confidence,
        "evidence": list(ev.evidence),
        "level_pct": None,
        "hours_to_limit": None,
        "recommended_actions": [],
    }
    if ev.category != "pump_failure":
        if ev.ongoing:
            d["recommended_actions"] = [{"type": "field_inspection", "asset_id": ev.asset_id}]
        return d
    if planned is None:
        return d

    st, plan, nothing = planned
    htl = st.hours_to_limit()
    arrivals = [st.response_min + i * st.cycle_min for i in range(plan.trips_per_truck)]
    d.update({
        "level_pct": round(st.level_pct, 1),
        "hours_to_limit": None if htl is None else {"p50": round(htl, 2)},
        "recommended_actions": plan.actions(),
        "plan_summary": plan.summary(),
        "est_cost": round(plan.cost, 2),
        "cost_breakdown": plan.breakdown,
        # SPEC: all trucks arrive together response_min after the call, then every cycle_min.
        "truck_arrivals_min": arrivals,
        "repair_remaining_h": round(st.horizon_min / 60, 2),
        "lost_revenue_per_hour": round(st.revenue_ph, 2),
        "do_nothing": {
            "cost": round(nothing.cost, 2),
            "shutdown_after_min": None if nothing.trips_at_min is None else round(nothing.trips_at_min),
        },
        "savings": round(nothing.cost - plan.cost, 2),
    })
    if st.already_shut:
        d["evidence"].append("Tank already at shutdown; wells are shut in until the repair ends")
    elif htl is not None:
        d["evidence"].append(f"Tank at {st.level_pct:.1f}%, reaches shutdown "
                             f"({st.shutdown_pct:g}%) in {htl:.1f} h if nothing is done")
    return d
