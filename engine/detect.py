from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from .calibrate import (
    decorrelation_steps,
    gate_z,
    robust_scale,
    rolling_mean,
    sample_interval_s,
    steps,
)
from .loader import Dataset, iter_facilities, series


# ---------------------------------------------------------------- pump failure

@dataclass(frozen=True)
class PumpFailure:
    facility_id: str
    pump_id: str
    onset: int          # ts_unix of first status-2 sample
    last_fault: int     # ts_unix of last status-2 sample in the run
    repair_end: int     # onset + expected_repair_hours.pump_failure
    ongoing: bool       # run still open at `now`


def detect_pump_failures(ds: Dataset, now: int | None = None) -> list[PumpFailure]:
    repair_s = ds.ops["expected_repair_hours"]["pump_failure"] * 3600
    events: list[PumpFailure] = []

    for item in iter_facilities(ds):
        fac = item["facility"]
        pump_id = fac["pump"]["id"]
        status = series(ds, pump_id, "status", now)
        if status.empty:
            continue

        ts = status.index.to_numpy()
        fault = status.to_numpy() == 2
        if not fault.any():
            continue

        padded = np.concatenate(([False], fault, [False]))
        diff = np.diff(padded.astype(np.int8))
        starts = np.flatnonzero(diff == 1)
        ends = np.flatnonzero(diff == -1) - 1

        for s, e in zip(starts, ends):
            onset = int(ts[s])
            events.append(PumpFailure(
                facility_id=fac["id"],
                pump_id=pump_id,
                onset=onset,
                last_fault=int(ts[e]),
                repair_end=onset + repair_s,
                ongoing=bool(e == len(fault) - 1),
            ))

    return events


# ---------------------------------------------------------------- pump degradation

@dataclass(frozen=True)
class PumpDegradation:
    facility_id: str
    pump_id: str
    onset: int          # back-dated hinge onset (when the decline started)
    detected: int       # first sample the rolling mean was confirmed low
    ongoing: bool
    drop_pct: float     # percent below the healthy ratio at detection
    confidence: float   # normal CDF of the detection's deviation, in sigma


def _run_segment_ids(s: np.ndarray) -> np.ndarray:
    """Segment id for each running sample; -1 when the pump is not running.
    A new segment starts at each non-running -> running transition."""
    running = s == 1
    starts = running & ~np.concatenate(([False], running[:-1]))
    return np.where(running, np.cumsum(starts), -1)


def _ramp_mask(ratio: np.ndarray, seg: np.ndarray, level: float) -> np.ndarray:
    """Within each run, mark samples before the ratio first reaches `level`."""
    mask = np.zeros(len(ratio), dtype=bool)
    for sid in np.unique(seg[seg >= 0]):
        idx = np.flatnonzero(seg == sid)
        ok = np.flatnonzero(ratio[idx] >= level)
        mask[idx[: (ok[0] if ok.size else len(idx))]] = True
    return mask


def _hinge_onset(ts: np.ndarray, ratio: np.ndarray, seg: np.ndarray, det: int) -> int:
    """Index of the start of a flat-then-linear decline that best fits the ratio,
    using only samples in the same running segment up to the detection."""
    m = np.isfinite(ratio) & (seg == seg[det])
    m[det + 1:] = False
    idx = np.flatnonzero(m)
    if idx.size < 2:
        return det

    t = ts[idx].astype(float)
    y = ratio[idx]
    # Candidate onset c = each sample; dt[c, k] = time from candidate c to sample k, clipped at 0.
    dt = np.clip(t[None, :] - t[:, None], 0, None)
    num = ((1 - y)[None, :] * dt).sum(axis=1)
    den = (dt ** 2).sum(axis=1)
    slope = np.where(den > 0, np.clip(num / np.where(den > 0, den, 1), 0, None), 0)
    sse = ((y[None, :] - (1 - slope[:, None] * dt)) ** 2).sum(axis=1)
    return int(idx[int(np.argmin(sse))])


def detect_pump_degradation(ds: Dataset, now: int | None = None) -> list[PumpDegradation]:
    events: list[PumpDegradation] = []

    for item in iter_facilities(ds):
        fac = item["facility"]
        pump = fac["pump"]
        pid, pipe_id = pump["id"], fac["pipeline"]["id"]

        st = series(ds, pid, "status", now)
        if st.empty:
            continue
        ts, s, n = st.index.to_numpy(), st.to_numpy(), len(st)
        flow = series(ds, pid, "flow_bpd", now).reindex(ts).to_numpy()
        recv = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()

        running = np.zeros(n, dtype=bool)
        running[1:] = (s[1:] == 1) & (s[:-1] == 1)
        interval = sample_interval_s(ts)
        repair_steps = steps(ds.ops["expected_repair_hours"]["pump_failure"] * 3600, interval)

        ratio = np.where(running, flow / pump["max_flow_bpd"], np.nan)
        gap = np.where(running, flow - recv, np.nan)

        # Drop leak-like samples, using this dataset's own gap distribution.
        w = decorrelation_steps(ratio[running], repair_steps)
        zg = gate_z(np.isfinite(ratio).sum() / w)
        gs = robust_scale(gap)
        normal = np.isfinite(gap) & (gap <= gs.center + zg * gs.sigma)
        ratio = np.where(normal, ratio, np.nan)

        seg = _run_segment_ids(s)
        rs = rolling_mean(ratio, w)          # NaN unless w consecutive normal running samples
        if not np.isfinite(rs).any():
            # Not enough contiguous healthy running data to calibrate this pump yet.
            # Report nothing rather than guess a baseline.
            continue
        base = robust_scale(rs)
        z = gate_z(np.isfinite(rs).sum() / w)
        level = base.center - z * base.sigma

        # Second pass: drop each run's ramp-up, then recompute the rolling mean.
        ratio = np.where(_ramp_mask(ratio, seg, level), np.nan, ratio)
        rs = rolling_mean(ratio, w)
        below = np.where(np.isfinite(rs), rs < level, False)

        # Confirmed: w consecutive samples below the level.
        confirmed = np.flatnonzero(np.convolve(below.astype(int), np.ones(w, int))[:n] == w)

        i_next = 0
        for det in confirmed:
            if det < i_next:
                continue
            j = det + 1
            while j < n and not ((np.isfinite(rs[j]) and rs[j] > base.center) or s[j] == 2):
                j += 1
            onset_idx = _hinge_onset(ts, ratio, seg, det)
            z_drop = (base.center - rs[det]) / base.sigma
            events.append(PumpDegradation(
                facility_id=fac["id"],
                pump_id=pid,
                onset=int(ts[onset_idx]),
                detected=int(ts[det]),
                ongoing=j >= n,
                drop_pct=float((1 - rs[det] / base.center) * 100),
                confidence=float(NormalDist().cdf(z_drop)),
            ))
            i_next = j

    return events