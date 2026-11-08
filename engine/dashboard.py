"""Everything the dashboard page needs in one payload, built only from the challenge data.

Field names follow the data files (network.json, ops.json, telemetry.csv metrics) so the
frontend works with the same vocabulary as the challenge docs. Values that are not raw data
are computed with the formulas in docs/SPEC.md, and each one says where it comes from.
"""
from __future__ import annotations

from .detect import healthy_reference
from .events import analyze
from .loader import Dataset, iter_facilities, series

# Telemetry pump status codes (docs/SPEC.md): 0 stopped, 1 running, 2 fault.
PUMP_STATE = {0: "stopped", 1: "running", 2: "fault"}


def _latest(ds: Dataset, asset_id: str, metric: str, now: int):
    s = series(ds, asset_id, metric, now)
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return int(v) if metric == "status" else v   # status codes are integers in the spec


def dashboard(ds: Dataset, now: int | None = None) -> dict:
    result = analyze(ds, now)
    now = result["now_unix"]
    ref = healthy_reference(ds, now)
    limits = ds.network["defaults"]["tank_limits_pct"]

    ongoing: dict[str, list[dict]] = {}
    for ev in result["alerts"]:
        ongoing.setdefault(ev["facility_id"], []).append(ev)

    facilities, by_system = [], {}
    for item in iter_facilities(ds):
        fac, system = item["facility"], item["system"]
        tank, pump, pipe = fac["tank"], fac["pump"], fac["pipeline"]
        disposal_psi = system["disposal_site"]["pressure_psi"]
        status = _latest(ds, pump["id"], "status", now)
        issues = ongoing.get(fac["id"], [])
        cats = {e["category"] for e in issues}

        facilities.append({
            "id": fac["id"],
            "system_id": system["id"],
            "lat": fac["lat"],
            "lon": fac["lon"],
            "wells": [{
                "id": w["id"],
                "status": _latest(ds, w["id"], "status", now),        # 1 producing, 0 shut in
                "water_bpd": _latest(ds, w["id"], "water_bpd", now),
                "baseline_water_bpd": w["baseline_water_bpd"],
                "oil_bpd": w["oil_bpd"],
                "gas_mcfd": w["gas_mcfd"],
            } for w in fac["wells"]],
            "inflow_bpd": _latest(ds, fac["id"], "inflow_bpd", now),
            "tank": {
                "id": tank["id"],
                "capacity_bbl": tank["capacity_bbl"],
                "level_pct": _latest(ds, tank["id"], "level_pct", now),
                "warning_pct": limits["warning"],
                "shutdown_pct": limits["shutdown"],
            },
            "pump": {
                "id": pump["id"],
                "status": None if status is None else int(status),
                "state": PUMP_STATE.get(int(status)) if status is not None else None,
                "flow_bpd": _latest(ds, pump["id"], "flow_bpd", now),
                "max_flow_bpd": pump["max_flow_bpd"],
                "discharge_psi": _latest(ds, pump["id"], "discharge_psi", now),
                "start_level_pct": pump["start_level_pct"],
                "stop_level_pct": pump["stop_level_pct"],
                # From detection: "failed", "degraded" or "ok".
                "health": ("failed" if "pump_failure" in cats
                           else "degraded" if "pump_degradation" in cats else "ok"),
            },
            "pipeline": {
                "id": pipe["id"],
                "receive_flow_bpd": _latest(ds, pipe["id"], "receive_flow_bpd", now),
                "pressure_psi": _latest(ds, pipe["id"], "pressure_psi", now),
                "max_bpd": pipe.get("max_bpd"),
                "max_pressure_psi": pipe.get("max_pressure_psi"),
                # Healthy pressure while the pump runs: disposal pressure + offset measured
                # from this dataset (SPEC calls the +50 psi a placeholder, so it is not assumed).
                "normal_running_pressure_psi": round(disposal_psi + ref.p_offset, 1),
                "health": "leak" if "pipeline_leak" in cats else "ok",
            },
            "issues": issues,   # events.json-shaped, most urgent first
        })

        bucket = by_system.setdefault(system["id"], {"system": system, "assigned": []})
        for e in issues:
            for a in e.get("recommended_actions", []):
                if a["type"] == "dispatch_truck":
                    bucket["assigned"].append({"facility_id": a["facility_id"], "trucks": a["trucks"],
                                               "trips_per_truck": a["trips_per_truck"]})

    systems = []
    for sid, b in by_system.items():
        system = b["system"]
        fleet = ds.ops["systems"][sid]["emergency_fleet_size"]
        used = sum(a["trucks"] for a in b["assigned"])
        systems.append({
            "id": sid,
            "center": system.get("center"),
            "truck_yard": system.get("truck_yard"),
            "disposal_site": system["disposal_site"],
            "emergency_fleet_size": fleet,
            "trucks_assigned": b["assigned"],
            "trucks_free": fleet - used,
        })

    tel_ts = ds.telemetry.index.get_level_values("ts_unix")
    return {
        "dataset": ds.name,
        "now_ts": result["now_ts"],
        "now_unix": now,
        "time_range": {"start_unix": int(tel_ts.min()), "end_unix": int(tel_ts.max())},
        "units": ds.network.get("meta", {}).get("units"),
        "prices": ds.ops["prices"],
        "emergency_trucking": ds.ops["emergency_trucking"],
        "expected_repair_hours": ds.ops["expected_repair_hours"],
        "systems": systems,
        "facilities": facilities,
        "alerts": result["alerts"],
    }
