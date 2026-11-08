"""Countdown to shutdown and the cheapest response for ongoing pump failures.

Rules follow docs/SPEC.md#plans:
- trucks are all called at plan start and first arrive response_min later, then every cycle_min;
  each arrival removes truck_capacity_bbl per truck (never more than is in the tank);
  every trip must arrive before the repair ends; a system's trucks are shared.
- wells can be shut in at any time until the repair ends; cost = lost oil + gas revenue.
- if the tank reaches shutdown, all wells shut in until the repair ends.
Everything (prices, fleet, times, capacities, limits) is read from the dataset files.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .loader import Dataset, iter_facilities, series

EPS = 1e-9


@dataclass(frozen=True)
class Well:
    id: str
    water_bpm: float        # live water rate, bbl per minute
    revenue_ph: float       # oil + gas revenue per hour


@dataclass(frozen=True)
class TankState:
    """Everything the planner needs for one failed pump, measured at `now`."""
    system_id: str
    facility_id: str
    level_pct: float
    capacity_bbl: float
    shutdown_pct: float
    horizon_min: float      # repair time remaining
    response_min: float
    cycle_min: float
    wells: tuple[Well, ...]
    already_shut: bool      # tank had already reached shutdown at `now`

    @property
    def volume(self) -> float:
        return self.level_pct / 100 * self.capacity_bbl

    @property
    def limit(self) -> float:
        return self.shutdown_pct / 100 * self.capacity_bbl

    @property
    def inflow_bpm(self) -> float:
        return sum(w.water_bpm for w in self.wells)

    @property
    def revenue_ph(self) -> float:
        return sum(w.revenue_ph for w in self.wells)

    def hours_to_limit(self) -> float | None:
        if self.already_shut:
            return 0.0
        if self.inflow_bpm <= 0:
            return None
        return (self.limit - self.volume) / self.inflow_bpm / 60


@dataclass
class Plan:
    facility_id: str
    trucks: int = 0
    trips_per_truck: int = 0
    shut_wells: tuple[str, ...] = ()
    shut_after_min: float = 0.0
    trips_at_min: float | None = None   # when the tank still reaches shutdown under this plan
    cost: float = 0.0
    breakdown: dict = field(default_factory=dict)
    compared: int = 1                    # candidate plans evaluated to find this one

    def actions(self) -> list[dict]:
        out = []
        if self.trucks:
            out.append({"type": "dispatch_truck", "facility_id": self.facility_id,
                        "trucks": self.trucks, "trips_per_truck": self.trips_per_truck})
        if self.shut_wells:
            out.append({"type": "shut_in_wells", "wells": list(self.shut_wells),
                        "start_after_min": round(self.shut_after_min)})
        return out or [{"type": "none"}]

    def summary(self) -> str:
        parts = []
        if self.trucks:
            parts.append(f"{self.trucks} truck{'s' * (self.trucks > 1)}, "
                         f"{self.trips_per_truck} trip{'s' * (self.trips_per_truck > 1)}"
                         f"{' each' if self.trucks > 1 else ''}")
        if self.shut_wells:
            parts.append(f"shut in {', '.join(self.shut_wells)} at +{round(self.shut_after_min)} min")
        if not parts:
            parts.append("no action")
        if self.trips_at_min is not None:
            parts.append(f"tank reaches shutdown at +{round(self.trips_at_min)} min")
        return " + ".join(parts) + f" (~${self.cost:,.0f})"


# ---------------------------------------------------------------- state at now

def tank_state(ds: Dataset, item: dict, repair_end: int, now: int) -> TankState:
    fac = item["facility"]
    prices = ds.ops["prices"]
    shutdown = ds.network["defaults"]["tank_limits_pct"]["shutdown"]
    level = float(series(ds, fac["tank"]["id"], "level_pct", now).iloc[-1])

    wells = []
    any_producing = False
    for w in fac["wells"]:
        recent = series(ds, w["id"], "water_bpd", now).iloc[-3:]   # last 15 min, smooths noise
        producing = series(ds, w["id"], "status", now).iloc[-1] == 1
        any_producing |= bool(producing)
        wells.append(Well(
            id=w["id"],
            # A shut-in well still counts at its baseline: it resumes when the repair ends.
            water_bpm=(float(recent.mean()) if producing else w["baseline_water_bpd"]) / 1440,
            revenue_ph=(w["oil_bpd"] * prices["oil_per_bbl"]
                        + w["gas_mcfd"] * prices["gas_per_mcf"]) / 24,
        ))
    return TankState(
        system_id=item["system"]["id"],
        facility_id=fac["id"],
        level_pct=level,
        capacity_bbl=fac["tank"]["capacity_bbl"],
        shutdown_pct=shutdown,
        horizon_min=max(0.0, (repair_end - now) / 60),
        response_min=item["response_min"],
        cycle_min=item["cycle_min"],
        wells=tuple(wells),
        already_shut=not any_producing and level >= shutdown - 0.5,
    )


# ---------------------------------------------------------------- one facility

def simulate(st: TankState, trucks: int, trips: int, cap: float,
             shut: tuple[Well, ...], t_shut: float) -> float | None:
    """Returns the minute the tank reaches shutdown, or None if it never does."""
    q_full = st.inflow_bpm
    q_after = q_full - sum(w.water_bpm for w in shut)
    arrivals = [st.response_min + i * st.cycle_min for i in range(trips)] if trucks else []
    marks = sorted(set([t for t in arrivals] + ([t_shut] if shut else []) + [st.horizon_min]))

    t, v = 0.0, st.volume
    for m in marks:
        m = min(m, st.horizon_min)
        q = q_after if shut and t >= t_shut else q_full
        if q > 0 and v + q * (m - t) >= st.limit - EPS:
            return t + max(0.0, (st.limit - v) / q)
        v += q * (m - t)
        t = m
        if m in arrivals:
            v = max(0.0, v - trucks * cap * arrivals.count(m))
        if t >= st.horizon_min:
            break
    return None


def plan_cost(st: TankState, trucks: int, trips: int, shut: tuple[Well, ...], t_shut: float,
              truck_cap: float, trip_cost: float) -> Plan:
    trip_t = simulate(st, trucks, trips, truck_cap, shut, t_shut)
    truck_cost = trucks * trips * trip_cost
    shut_rev = sum(w.revenue_ph for w in shut)
    vol_cost = shut_rev * (st.horizon_min - t_shut) / 60 if shut else 0.0
    auto_cost = 0.0
    if trip_t is not None:
        # Wells not already shut in by the plan are forced off until the repair ends.
        still_on = st.revenue_ph - (shut_rev if shut and t_shut <= trip_t else 0.0)
        auto_cost = still_on * (st.horizon_min - trip_t) / 60
    return Plan(st.facility_id, trucks if trips else 0, trips if trucks else 0,
                tuple(w.id for w in shut), t_shut, trip_t,
                truck_cost + vol_cost + auto_cost,
                {"trucks": truck_cost, "planned_shut_in": round(vol_cost, 2),
                 "automatic_shut_in": round(auto_cost, 2)})


def best_plan(st: TankState, max_trucks: int, truck_cap: float, trip_cost: float,
              allow_shut: bool = True, min_trucks: int = 0) -> Plan:
    """Cheapest plan using at most max_trucks trucks (and at least min_trucks).
    allow_shut=False restricts the search to trucking only."""
    if st.already_shut or st.horizon_min <= 0:
        return Plan(st.facility_id, cost=st.revenue_ph * st.horizon_min / 60,
                    breakdown={"automatic_shut_in": round(st.revenue_ph * st.horizon_min / 60, 2)})

    max_trips = 0
    while st.response_min + max_trips * st.cycle_min < st.horizon_min:
        max_trips += 1

    subsets = [()]
    if allow_shut:
        subsets += [c for r in range(1, len(st.wells) + 1) for c in itertools.combinations(st.wells, r)]
    best: Plan | None = None
    compared = 0
    if min_trucks > 0 and max_trips == 0:
        return None   # no truck can arrive before the repair ends
    for k in range(min_trucks, max_trucks + 1):
        for m in ([0] if k == 0 else range(1, max_trips + 1)):
            for shut in subsets:
                if not shut:
                    cands = [plan_cost(st, k, m, (), 0.0, truck_cap, trip_cost)]
                else:
                    cands = [plan_cost(st, k, m, shut, 0.0, truck_cap, trip_cost)]
                    t = _latest_safe_shut(st, k, m, shut, truck_cap)
                    if t is not None:
                        cands.append(plan_cost(st, k, m, shut, t, truck_cap, trip_cost))
                compared += len(cands)
                for p in cands:
                    if best is None or p.cost < best.cost - 1e-6:
                        best = p
    best.compared = compared
    return best


def compare_options(st: TankState, fleet: int, truck_cap: float, trip_cost: float) -> list[dict]:
    """The pure strategies next to each other, so the operator can see why the plan wins.
    Each is the cheapest plan of its kind."""
    def row(label, p):
        return None if p is None else {"label": label, "summary": p.summary(), "cost": round(p.cost, 2),
                                       "reaches_shutdown": p.trips_at_min is not None}
    rows = [row("Do nothing", do_nothing(st, truck_cap, trip_cost)),
            row("Shut in wells only", best_plan(st, 0, truck_cap, trip_cost))]
    if fleet:
        rows.append(row("Trucks only", best_plan(st, fleet, truck_cap, trip_cost, allow_shut=False, min_trucks=1)))
    return [r for r in rows if r]


def _latest_safe_shut(st, k, m, shut, cap) -> float | None:
    """Latest whole minute to shut these wells so the tank never reaches shutdown."""
    if simulate(st, k, m, cap, shut, 0.0) is not None:
        return None
    lo, hi = 0, int(st.horizon_min)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if simulate(st, k, m, cap, shut, float(mid)) is None:
            lo = mid
        else:
            hi = mid - 1
    return float(lo)


# ---------------------------------------------------------------- shared trucks

def plan_system(states: list[TankState], fleet: int, truck_cap: float,
                trip_cost: float) -> dict[str, Plan]:
    """Split one system's fleet across its ongoing failures for the lowest total cost."""
    table = [[best_plan(st, k, truck_cap, trip_cost) for k in range(fleet + 1)] for st in states]
    best_total, best_alloc = None, None
    for alloc in itertools.product(range(fleet + 1), repeat=len(states)):
        if sum(alloc) > fleet:
            continue
        total = sum(table[i][k].cost for i, k in enumerate(alloc))
        if best_total is None or total < best_total - 1e-6:
            best_total, best_alloc = total, alloc
    return {st.facility_id: table[i][best_alloc[i]] for i, st in enumerate(states)}


def do_nothing(st: TankState, truck_cap: float, trip_cost: float) -> Plan:
    """The tank fills until shutdown; then every well is off until the repair ends."""
    if st.already_shut or st.horizon_min <= 0:
        return best_plan(st, 0, truck_cap, trip_cost)
    return plan_cost(st, 0, 0, (), 0.0, truck_cap, trip_cost)


def plan_ongoing_failures(ds: Dataset, failures: list, now: int) -> dict[str, tuple]:
    """failures: ongoing pump_failure events.
    Returns facility_id -> (state, recommended plan, do-nothing plan, decision info)."""
    items = {it["facility"]["id"]: it for it in iter_facilities(ds)}
    repair_s = ds.ops["expected_repair_hours"]["pump_failure"] * 3600
    truck = ds.ops["emergency_trucking"]
    by_system: dict[str, list[TankState]] = {}
    for ev in failures:
        st = tank_state(ds, items[ev.facility_id], ev.onset + repair_s, now)
        by_system.setdefault(st.system_id, []).append(st)

    out = {}
    for sid, states in by_system.items():
        fleet = ds.ops["systems"][sid]["emergency_fleet_size"]
        cap, cost = truck["truck_capacity_bbl"], truck["cost_per_trip"]
        plans = plan_system(states, fleet, cap, cost)
        splits = sum(1 for a in itertools.product(range(fleet + 1), repeat=len(states)) if sum(a) <= fleet)
        for st in states:
            p = plans[st.facility_id]
            info = {
                "options": compare_options(st, fleet, cap, cost),
                "plans_compared": p.compared,
                "fleet_size": fleet,
                "sharing_with": [s.facility_id for s in states if s is not st],
                "fleet_splits_compared": splits if len(states) > 1 else None,
            }
            out[st.facility_id] = (st, p, do_nothing(st, cap, cost), info)
    return out
