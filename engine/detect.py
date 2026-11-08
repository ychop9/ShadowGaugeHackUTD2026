from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

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
    confidence: float = 0.99


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


# ---------------------------------------------------------------- pipeline leak

LEAK_PRESSURE_OFFSET_PSI = -25.0   # pressure - (disposal + 50) below this is a leak sample
LEAK_FLOW_GAP_BPD = 80.0           # pump flow - pipeline receive above this is a leak sample
LEAK_OPEN_SAMPLES = 3              # consecutive flagged samples to open (15 min)
LEAK_RESOLVE_SAMPLES = 6           # consecutive normal running samples to resolve


@dataclass(frozen=True)
class PipelineLeak:
    facility_id: str
    pipeline_id: str
    onset: int          # first flagged sample
    last_flagged: int
    ongoing: bool
    observable: bool    # False if the pump was off at the last sample
    confidence: float   # min(0.99, 0.6 + 0.1 * flagged samples)


def detect_pipeline_leaks(ds: Dataset, now: int | None = None) -> list[PipelineLeak]:
    events: list[PipelineLeak] = []

    for item in iter_facilities(ds):
        system = item["system"]
        fac = item["facility"]
        pump_id = fac["pump"]["id"]
        pipe_id = fac["pipeline"]["id"]
        disposal_psi = system["disposal_site"]["pressure_psi"]

        pump_status = series(ds, pump_id, "status", now)
        if pump_status.empty:
            continue
        ts = pump_status.index.to_numpy()

        pump_flow = series(ds, pump_id, "flow_bpd", now).reindex(ts).to_numpy()
        recv_flow = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()
        pressure = series(ds, pipe_id, "pressure_psi", now).reindex(ts).to_numpy()
        status = pump_status.to_numpy()

        running = np.zeros(len(ts), dtype=bool)
        running[1:] = (status[1:] == 1) & (status[:-1] == 1)

        offset = pressure - (disposal_psi + 50)
        gap = pump_flow - recv_flow
        flagged = running & (offset < LEAK_PRESSURE_OFFSET_PSI) & (gap > LEAK_FLOW_GAP_BPD)
        normal = running & ~flagged

        events.extend(_leak_events(fac["id"], pipe_id, ts, flagged, normal, status))

    return events


def _leak_events(fac_id, pipe_id, ts, flagged, normal, status) -> list[PipelineLeak]:
    out: list[PipelineLeak] = []
    i, n = 0, len(ts)
    while i < n:
        if i + LEAK_OPEN_SAMPLES <= n and flagged[i:i + LEAK_OPEN_SAMPLES].all():
            onset_idx = i
            j = i + LEAK_OPEN_SAMPLES
            flagged_count = LEAK_OPEN_SAMPLES
            last_flagged_idx = j - 1
            calm = 0
            resolved = False
            while j < n:
                if flagged[j]:
                    flagged_count += 1
                    last_flagged_idx = j
                    calm = 0
                elif normal[j]:
                    calm += 1
                    if calm >= LEAK_RESOLVE_SAMPLES:
                        resolved = True
                        break
                j += 1
            observable = bool(status[-1] == 1) if j >= n else True
            out.append(PipelineLeak(
                facility_id=fac_id,
                pipeline_id=pipe_id,
                onset=int(ts[onset_idx]),
                last_flagged=int(ts[last_flagged_idx]),
                ongoing=not resolved,
                observable=observable,
                confidence=min(0.99, 0.6 + 0.1 * flagged_count),
            ))
            i = j
        else:
            i += 1
    return out

# ---------------------------------------------------------------- pump degradation

DEG_RATIO_WINDOW = 12        # valid running samples in the rolling mean
DEG_ENTER_BELOW = 0.985      # rolling mean below this starts the event
DEG_CONFIRM_SAMPLES = 6      # consecutive samples below threshold to confirm
DEG_RESOLVE_ABOVE = 0.995    # rolling mean above this resolves the event
DEG_BACKDATE_S = 48 * 3600   # hinge fit window before detection


@dataclass(frozen=True)
class PumpDegradation:
    facility_id: str
    pump_id: str
    onset: int          # back-dated hinge onset (when the decline started)
    detected: int       # first sample the rolling mean was confirmed low
    ongoing: bool
    drop_pct: float     # percent below max flow at detection
    confidence: float   # 0.5 at 1.5%, 0.9 at 4%, 0.99 at 8%+


def detect_pump_degradation(ds: Dataset, now: int | None = None) -> list[PumpDegradation]:
    events: list[PumpDegradation] = []

    for item in iter_facilities(ds):
        fac = item["facility"]
        pump = fac["pump"]
        pump_id = pump["id"]
        pipe_id = fac["pipeline"]["id"]

        status_s = series(ds, pump_id, "status", now)
        if status_s.empty:
            continue
        ts = status_s.index.to_numpy()
        status = status_s.to_numpy()
        n = len(ts)

        flow = series(ds, pump_id, "flow_bpd", now).reindex(ts).to_numpy()
        recv = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()

        running = np.zeros(n, dtype=bool)
        running[1:] = (status[1:] == 1) & (status[:-1] == 1)
        gap = flow - recv
        seg = _run_segment_ids(status)
        edge = _run_edge_mask(status)
        valid = running & ~edge & np.isfinite(flow) & (gap <= LEAK_FLOW_GAP_BPD)

        ratio = np.where(valid, flow / pump["max_flow_bpd"], np.nan)
        valid_idx = np.flatnonzero(valid)
        interval_s = int(np.median(np.diff(ts)))
        valid_idx = np.flatnonzero(valid)
        roll_full = np.full(n, np.nan)
        roll_full[valid_idx] = _rolling_contiguous(ts, ratio, valid_idx, interval_s)

        below = roll_full < DEG_ENTER_BELOW   # NaN compares False

        i = DEG_CONFIRM_SAMPLES - 1
        while i < n:
            if not below[i - DEG_CONFIRM_SAMPLES + 1 : i + 1].all():
                i += 1
                continue

            det = i
            onset_idx = _hinge_onset(ts, ratio, valid, seg, det)

            j = det + 1
            while j < n and not (roll_full[j] > DEG_RESOLVE_ABOVE or status[j] == 2):
                j += 1

            drop_pct = float((1 - roll_full[det]) * 100)
            events.append(PumpDegradation(
                facility_id=fac["id"],
                pump_id=pump_id,
                onset=int(ts[onset_idx]),
                detected=int(ts[det]),
                ongoing=j >= n,
                drop_pct=drop_pct,
                confidence=float(np.interp(drop_pct, [1.5, 4.0, 8.0], [0.5, 0.9, 0.99])),
            ))
            i = j

    return events


def _hinge_onset(ts, ratio, valid, seg, det):
    lo = np.searchsorted(ts, ts[det] - DEG_BACKDATE_S)
    mask = valid.copy()
    mask[:lo] = False
    mask[det + 1:] = False
    mask &= (seg == seg[det])   # back-date only within the current running segment
    idx = np.flatnonzero(mask)
    if len(idx) < 10:
        return det

    t = ts[idx].astype(float)
    y = ratio[idx]
    # candidate t0 = each sample; dt[c, k] = time since candidate c, clipped at 0
    dt = np.clip(t[None, :] - t[:, None], 0, None)
    num = ((1 - y)[None, :] * dt).sum(axis=1)
    den = (dt ** 2).sum(axis=1)
    slope = np.where(den > 0, np.clip(num / np.where(den > 0, den, 1), 0, None), 0)
    pred = 1 - slope[:, None] * dt
    sse = ((y[None, :] - pred) ** 2).sum(axis=1)
    best = int(np.argmin(sse))
    return int(idx[best])

DEG_EDGE_SAMPLES = 3   # samples masked at each end of a running run (ramp up/down)


def _run_edge_mask(status: np.ndarray) -> np.ndarray:
    n = len(status)
    running = status == 1
    mask = np.zeros(n, dtype=bool)
    starts = np.flatnonzero(running & np.concatenate(([True], ~running[:-1])))
    ends = np.flatnonzero(running & np.concatenate((~running[1:], [True])))
    for s in starts:
        mask[s:s + DEG_EDGE_SAMPLES] = True
    for e in ends:
        mask[max(0, e - DEG_EDGE_SAMPLES + 1):e + 1] = True
    return mask

DEG_MAX_SPAN_FACTOR = 1.5   # a 12-sample window may span at most 1.5x its nominal length


def _rolling_contiguous(ts, ratio, vi, interval_s):
    """Rolling mean over valid samples, NaN where the window spans a gap."""
    m = len(vi)
    out = np.full(m, np.nan)
    if m < DEG_RATIO_WINDOW:
        return out
    rolled = pd.Series(ratio[vi]).rolling(DEG_RATIO_WINDOW).mean().to_numpy()
    tv = ts[vi]
    span = np.full(m, np.inf)
    span[DEG_RATIO_WINDOW - 1:] = tv[DEG_RATIO_WINDOW - 1:] - tv[:m - DEG_RATIO_WINDOW + 1]
    max_span = DEG_MAX_SPAN_FACTOR * (DEG_RATIO_WINDOW - 1) * interval_s
    ok = span <= max_span
    out[ok] = rolled[ok]
    return out

def _run_segment_ids(status: np.ndarray) -> np.ndarray:
    """Segment id for each running sample; -1 when the pump is not running.
    A new segment starts at each non-running -> running transition."""
    running = status == 1
    starts = running & ~np.concatenate(([False], running[:-1]))
    return np.where(running, np.cumsum(starts), -1)