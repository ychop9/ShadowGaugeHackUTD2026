from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .calibrate import Scale, decorrelation_steps, gate_z, robust_scale, rolling_mean, sample_interval_s, steps
from .loader import Dataset, iter_facilities
from .signals import raw_pipeline_signals


@dataclass(frozen=True)
class LeakCal:
    w: int      # smoothing and persistence window, in samples
    p: Scale    # smoothed pressure on steady-running samples
    g: Scale    # smoothed flow gap on steady-running samples
    z: float    # gate, in sigma units


@dataclass(frozen=True)
class PipelineLeak:
    facility_id: str
    pipeline_id: str
    onset: int
    last_flagged: int
    ongoing: bool
    confidence: float


def calibrate_leak(ds: Dataset, item: dict, now: int | None) -> LeakCal:
    ts, running, p, g = raw_pipeline_signals(ds, item, now)
    repair_steps = steps(ds.ops["expected_repair_hours"]["pump_failure"] * 3600,
                         sample_interval_s(ts))
    w = decorrelation_steps(p[running], repair_steps)
    sp, sg = rolling_mean(p, w), rolling_mean(g, w)
    ok = np.isfinite(sp) & np.isfinite(sg)
    z = gate_z(ok.sum() / w)
    return LeakCal(w, robust_scale(sp), robust_scale(sg), z)


def detect_pipeline_leaks(ds: Dataset, now: int | None = None) -> list[PipelineLeak]:
    events: list[PipelineLeak] = []
    for item in iter_facilities(ds):
        fac = item["facility"]
        ts, running, p, g = raw_pipeline_signals(ds, item, now)
        cal = calibrate_leak(ds, item, now)
        sp, sg = rolling_mean(p, cal.w), rolling_mean(g, cal.w)
        flag = (sp < cal.p.center - cal.z * cal.p.sigma) & (sg > cal.g.center + cal.z * cal.g.sigma)
        flag = np.where(np.isfinite(flag), flag, False)
        events.extend(_episodes(fac, ts, flag, cal))
    return events


def _episodes(fac, ts, flag, cal: LeakCal) -> list[PipelineLeak]:
    out = []
    starts = np.flatnonzero(flag & ~np.concatenate(([False], flag[:-1])))
    i_next = 0
    for s in starts:
        if s < i_next:
            continue
        end = np.flatnonzero(~flag[s:])
        e = s + end[0] if end.size else len(flag)
        n_flag = int(flag[s:e].sum())
        out.append(PipelineLeak(
            facility_id=fac["id"],
            pipeline_id=fac["pipeline"]["id"],
            onset=int(ts[s]),
            last_flagged=int(ts[e - 1]),
            ongoing=e == len(flag),
            confidence=float(_N_cdf(cal.z)),
        ))
        i_next = e
    return out