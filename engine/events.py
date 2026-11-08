"""One call for the whole engine: detect, forecast, plan, and order for the alerts view.

    from engine.events import analyze
    result = analyze(load_dataset("data/history/snapshot_2026-10-08T1200"))

Events use the events.json shape from docs/SPEC.md, plus a few display fields.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from .detect import Event, detect_all
from .loader import Dataset, iter_facilities, last_ts
from .plan import (do_nothing, plan_ongoing_failures, plan_system,
                   repair_prior_s, tank_state)


def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analyze(ds: Dataset, now: int | None = None) -> dict:
    """`now` defaults to the last telemetry timestamp; pass an earlier one to time-travel."""
    now = last_ts(ds) if now is None else now
    found = sorted(detect_all(ds, now), key=lambda e: e.onset)

    # The repair prior needs closed failures too, so measure it before filtering to ongoing.
    pump_failures = [e for e in found if e.category == "pump_failure"]
    ongoing_failures = [e for e in pump_failures if e.ongoing]
    prior_s = repair_prior_s(ds, pump_failures)
    plans = plan_ongoing_failures(ds, ongoing_failures, now, prior_s)

    # Match plans to events by identity, not dataclass equality.
    ongoing_ids = {id(ev) for ev in ongoing_failures}

    # Onset decisions are planned together, in time order, so trucks used by earlier
    # decisions are not available to later ones.
    onset_plans = _onset_plans(ds, pump_failures, prior_s)

    events = []
    for n, ev in enumerate(found, start=1):
        planned = plans.get(ev.facility_id) if id(ev) in ongoing_ids else None
        d = _to_dict(ev, n, planned)
        if ev.category == "pump_failure":
            onset = onset_plans.get(id(ev))
            if onset is not None:
                _, plan, nothing = onset
                d["onset_recommendation"] = {
                    "decided_at": _iso(ev.onset),
                    "summary": plan.summary(),
                    "actions": plan.actions(),
                    "est_cost": round(plan.cost, 2),
                    "do_nothing_cost": round(nothing.cost, 2),
                    "do_nothing_shutdown_after_min":
                        None if nothing.trips_at_min is None else round(nothing.trips_at_min),
                }
        events.append(d)

    alerts = [e for e in events if e["status"] == "ongoing"]
    alerts.sort(key=lambda e: (
        e["category"] != "pump_failure",                              # failures first
        e["hours_to_limit"]["p50"] if e["hours_to_limit"] else float("inf"),
        -(e.get("lost_revenue_per_hour") or 0),                        # tie: costlier first
    ))
    return {"dataset": ds.name, "now_unix": now, "now_ts": _iso(now),
            "alerts": alerts, "events": events}


def _prior_before(pump_failures: list[Event], t: int, fallback_s: float) -> float:
    """Median repair time of pump failures that had closed strictly before time t.
    Uses nothing that happened at or after t. Falls back when no failure had closed yet."""
    closed = [f.end - f.onset for f in pump_failures
              if f.end is not None and f.end < t]
    return float(np.median(closed)) if closed else fallback_s


def _onset_plans(ds: Dataset, pump_failures: list[Event], fallback_s: float) -> dict:
    """Plan each pump failure as it would have been issued at its onset.

    Failures are processed in onset order. Each one sees only the trucks that earlier
    decisions have not yet committed. A committed truck is assumed busy until its last
    arrival. The observed recovery is never used, and the repair prior uses only failures
    that had closed by the onset.

    Returns id(event) -> (state, plan, do_nothing_plan).
    """
    items = {it["facility"]["id"]: it for it in iter_facilities(ds)}
    truck = ds.ops["emergency_trucking"]
    cap, cost = truck["truck_capacity_bbl"], truck["cost_per_trip"]
    busy: dict[str, list[int]] = {}      # system_id -> busy-until timestamps, one per truck
    out = {}
    for ev in sorted(pump_failures, key=lambda e: e.onset):
        sid = ev.system_id
        fleet = ds.ops["systems"][sid]["emergency_fleet_size"]
        in_use = [t for t in busy.get(sid, []) if t > ev.onset]
        free = max(0, fleet - len(in_use))

        prior_s = _prior_before(pump_failures, ev.onset, fallback_s)
        st = tank_state(ds, items[ev.facility_id], ev.onset + int(prior_s), ev.onset)
        plan = plan_system([st], free, cap, cost)[st.facility_id]
        nothing = do_nothing(st, cap, cost)
        out[id(ev)] = (st, plan, nothing)

        if plan.trucks:
            last_arrival_min = st.response_min + (plan.trips_per_truck - 1) * st.cycle_min
            until = ev.onset + int(last_arrival_min * 60)
            busy.setdefault(sid, []).extend([until] * plan.trucks)
    return out


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