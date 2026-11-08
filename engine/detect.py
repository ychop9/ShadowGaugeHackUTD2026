"""Detect pump failures, pump degradation and pipeline leaks from sensor readings alone.

Every reference value comes from the dataset's own files:
- pump flow is compared with the pump's `max_flow_bpd` (network.json),
- the flow gap (pump flow - pipeline receive flow) should be zero (conservation of water),
- pipeline pressure is compared with the network's typical running offset above the disposal
  site's `pressure_psi`, measured from this dataset's telemetry.
Noise levels, the healthy flow reference and the alarm gate are measured from the dataset too,
so nothing is tuned to the labelled events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from .loader import Dataset, iter_facilities, sample_interval_s, series

_N = NormalDist()
MAD_TO_SIGMA = 1 / _N.inv_cdf(0.75)  # converts a median absolute deviation to a std dev
FAULT, RUNNING = 2, 1                # pump status codes from the spec


@dataclass
class Event:
    category: str            # pump_failure | pump_degradation | pipeline_leak
    system_id: str
    facility_id: str
    asset_id: str
    onset: int               # ts_unix
    end: int | None          # ts_unix when resolved, None when ongoing
    confidence: float
    evidence: list[str] = field(default_factory=list)
    impact: dict = field(default_factory=dict)   # measured size of the problem (slow problems)

    @property
    def ongoing(self) -> bool:
        return self.end is None


# ---------------------------------------------------------------- pump failure

def detect_pump_failures(ds: Dataset, now: int | None = None) -> list[Event]:
    """A pump failure is a run of status-2 samples. It ends at the start of the first full
    window of running samples whose mean flow ratio is back inside the healthy band measured
    from this dataset (see healthy_reference). If no such recovery is in the data, the event
    is ongoing. No ops.json value is used here."""
    cal = healthy_reference(ds, now)
    gate = cal.r_ref - cal.z * cal.sd_ratio / np.sqrt(cal.window)
    events = []
    for item in iter_facilities(ds):
        fac = item["facility"]
        pump = fac["pump"]
        status = series(ds, pump["id"], "status", now)
        flow = series(ds, pump["id"], "flow_bpd", now).reindex(status.index)
        ratio = flow / pump["max_flow_bpd"]
        running = ((status == RUNNING) & (flow > 0)).astype(float)
        ts = status.index.to_numpy()
        for s, e in _runs((status == FAULT).to_numpy()):
            onset = int(ts[s])
            end = _recovery_ts(ratio, running, gate, cal.window, start=e + 1)
            evidence = [f"Pump reports fault status since {_hhmm(onset)} UTC"]
            if end is None:
                evidence.append("No recovery in telemetry yet; repair end unknown")
            else:
                evidence.append(f"Pump back in healthy flow range at {_hhmm(end)} UTC")
            events.append(Event(
                category="pump_failure",
                system_id=item["system"]["id"],
                facility_id=fac["id"],
                asset_id=pump["id"],
                onset=onset,
                end=end,
                confidence=1.0,
                evidence=evidence,
            ))
    return events


def _recovery_ts(ratio: pd.Series, running: pd.Series, gate: float, w: int,
                 start: int) -> int | None:
    """First timestamp of a full window of running samples, starting at or after position
    `start`, whose mean flow ratio is at or above `gate`. Returns the window's first sample."""
    r = ratio.iloc[start:]
    run = running.iloc[start:]
    if len(r) < w:
        return None
    mean_ok = (r.rolling(w, min_periods=w).mean() >= gate).to_numpy()
    all_running = (run.rolling(w, min_periods=w).min() == 1).to_numpy()
    hits = np.flatnonzero(mean_ok & all_running)
    if len(hits) == 0:
        return None
    return int(r.index[hits[0] - w + 1])


# ---------------------------------------------------------------- shared calibration

@dataclass(frozen=True)
class Calibration:
    interval_s: int    # telemetry sample interval
    window: int        # running samples averaged per decision (one hour)
    z: float           # gate in standard deviations of the window mean
    p_offset: float    # healthy pipeline pressure above disposal while running, psi
    r_ref: float       # healthy running flow ratio (flow / max_flow_bpd), measured
    sd_ratio: float    # per-sample noise of pump flow / max_flow_bpd
    sd_gap: float      # per-sample noise of the flow gap fraction
    sd_p: float        # per-sample noise of pipeline pressure, psi


def _running_frame(ds: Dataset, item: dict, now: int | None) -> pd.DataFrame:
    """Signals for one facility, restricted to samples where the pump is running."""
    fac = item["facility"]
    pump, pipe = fac["pump"], fac["pipeline"]
    disposal = item["system"]["disposal_site"]["pressure_psi"]
    status = series(ds, pump["id"], "status", now)
    flow = series(ds, pump["id"], "flow_bpd", now)
    recv = series(ds, pipe["id"], "receive_flow_bpd", now)
    pres = series(ds, pipe["id"], "pressure_psi", now)
    df = pd.DataFrame({
        "ratio": flow / pump["max_flow_bpd"],
        "gap": (flow - recv) / flow.where(flow > 0),
        "p_off": pres - disposal,
    })
    return df[(status == RUNNING) & (flow > 0)]


def _robust_sd(x: pd.Series) -> float:
    return float(MAD_TO_SIGMA * (x - x.median()).abs().median())


def calibrate(ds: Dataset, frames: dict[str, pd.DataFrame], now: int | None) -> Calibration:
    """Network-wide noise, healthy reference and gate. Medians and MADs ignore the minority
    of samples that are inside problems, so no labels are needed."""
    allrun = pd.concat(frames.values())
    interval = sample_interval_s(ds)
    window = max(1, round(3600 / interval))
    n_windows = max(2.0, len(allrun) / window)
    z = _N.inv_cdf(1 - 1 / n_windows)  # about one false window expected network-wide
    return Calibration(
        interval_s=interval,
        window=window,
        z=z,
        p_offset=float(allrun["p_off"].median()),
        r_ref=float(allrun["ratio"].median()),
        sd_ratio=_robust_sd(allrun["ratio"]),
        sd_gap=_robust_sd(allrun["gap"]),
        sd_p=_robust_sd(allrun["p_off"]),
    )


# ---------------------------------------------------------------- slow problems

def _episodes(df: pd.DataFrame, score: pd.Series, cal: Calibration, last_ts: int):
    """score = z of the hourly mean (positive = abnormal). Confirmed when above the gate
    for a full window; ends after a full window back below it.
    Yields (onset_ts, end_ts or None, peak_z, latest_z)."""
    w = cal.window
    c = max(1, w // 4)                          # samples back below the gate to call it over
    above = (score > cal.z).to_numpy()
    if len(above) < w:
        return
    ts = df.index.to_numpy()
    sc = score.to_numpy()
    confirm = np.convolve(above, np.ones(w, int), "full")[: len(above)] >= w
    clear = np.convolve(~above, np.ones(c, int), "full")[: len(above)] >= c

    def back(idx: int, floor: int, n: int) -> int:
        """Step back n samples from idx, staying >= floor and within n samples of clock time
        (the pump may have been off in between)."""
        out = max(floor, idx - n)
        while out < idx and ts[out] < ts[idx] - n * cal.interval_s:
            out += 1
        return out

    i = 0
    while i < len(above):
        if not confirm[i]:
            i += 1
            continue
        start = i - w + 1                       # first sample of the confirming run
        onset_idx = back(start, 0, w - 1)       # the first abnormal window began here
        j = i
        while j < len(above) and not clear[j]:
            j += 1
        if j < len(above):
            first_clear = j - c + 1
            end_ts = int(ts[back(first_clear, start, w // 2)])  # mean lags the repair by ~w/2
            seg = sc[start:first_clear]
        else:
            end_ts = None
            seg = sc[start:]
        yield int(ts[onset_idx]), end_ts, float(np.nanmax(seg)), float(sc[-1])
        i = j + 1


def _confidence(z_obs: float, cal: Calibration) -> float:
    """Probability that the true shift is beyond the gate, given the observed z."""
    return round(_N.cdf(z_obs - cal.z), 3)


def detect_slow_problems(ds: Dataset, now: int | None = None,
                         failures: list[Event] = ()) -> list[Event]:
    """failures: pump failures already found. A degrading pump that fails is two events,
    so its degradation ends when the failure starts."""
    fail_onsets: dict[str, list[int]] = {}
    for f in failures:
        fail_onsets.setdefault(f.facility_id, []).append(f.onset)
    items = list(iter_facilities(ds))
    frames = {it["facility"]["id"]: _running_frame(ds, it, now) for it in items}
    cal = calibrate(ds, frames, now)
    w, root_w = cal.window, np.sqrt(cal.window)
    events = []
    for it in items:
        fac = it["facility"]
        df = frames[fac["id"]]
        if len(df) < w:
            continue
        mean = df.rolling(w, min_periods=w).mean()
        last = int(df.index[-1])

        # Degradation: hourly mean flow below the measured healthy running flow.
        z_deg = (cal.r_ref - mean["ratio"]) / (cal.sd_ratio / root_w)
        for onset, end, peak, latest in _episodes(df, z_deg, cal, last):
            cut = [t for t in fail_onsets.get(fac["id"], []) if t > onset and (end is None or t < end)]
            if cut:
                end = min(cut)
            ref = mean.loc[:end].iloc[-1] if end else mean.iloc[-1]
            drop = 100 * (1 - ref["ratio"])
            events.append(Event(
                "pump_degradation", it["system"]["id"], fac["id"], fac["pump"]["id"],
                onset, end, _confidence(latest if end is None else peak, cal),
                [f"Pump moving {drop:.1f}% less than its rated {fac['pump']['max_flow_bpd']:,} bpd "
                 f"while running", "Pipeline flow matches pump flow, so the water is not leaking"],
                {"flow_pct_of_rated": round(100 * ref["ratio"], 1),
                 "pumping_bpd": round(ref["ratio"] * fac["pump"]["max_flow_bpd"]),
                 "rated_bpd": fac["pump"]["max_flow_bpd"]},
            ))

        # Leak: water goes missing (gap up) AND pipeline pressure drops. Both must agree.
        z_gap = mean["gap"] / (cal.sd_gap / root_w)
        z_p = (cal.p_offset - mean["p_off"]) / (cal.sd_p / root_w)
        z_leak = np.minimum(z_gap, z_p)
        for onset, end, peak, latest in _episodes(df, z_leak, cal, last):
            ref = mean.loc[:end].iloc[-1] if end else mean.iloc[-1]
            events.append(Event(
                "pipeline_leak", it["system"]["id"], fac["id"], fac["pipeline"]["id"],
                onset, end, _confidence(latest if end is None else peak, cal),
                [f"{100 * ref['gap']:.1f}% of pumped water is not arriving at disposal",
                 f"Pipeline pressure {cal.p_offset - ref['p_off']:.0f} psi below normal"],
                {"lost_pct": round(100 * ref["gap"], 1),
                 # water escaping per day of pumping: missing fraction x pumped flow
                 "lost_bpd_while_pumping": round(ref["gap"] * ref["ratio"] * fac["pump"]["max_flow_bpd"]),
                 "pressure_drop_psi": round(cal.p_offset - ref["p_off"], 1)},
            ))

    # Slow problems are only visible while water is flowing. Say so when the pump is idle.
    pump_of = {it["facility"]["id"]: it["facility"]["pump"]["id"] for it in items}
    for ev in events:
        df = frames[ev.facility_id]
        status = series(ds, pump_of[ev.facility_id], "status", now)
        if ev.ongoing and int(df.index[-1]) < int(status.index[-1]):
            ev.evidence.append(f"Pump not running since {_hhmm(int(df.index[-1]))} UTC; "
                               "can't confirm whether this is still happening until it restarts")
    return events


def healthy_reference(ds: Dataset, now: int | None = None) -> Calibration:
    """The healthy reference values the detectors compare against, measured from this dataset."""
    frames = {it["facility"]["id"]: _running_frame(ds, it, now) for it in iter_facilities(ds)}
    return calibrate(ds, frames, now)


def detect_all(ds: Dataset, now: int | None = None) -> list[Event]:
    failures = detect_pump_failures(ds, now)
    return failures + detect_slow_problems(ds, now, failures)


# ---------------------------------------------------------------- helpers

def _runs(mask: np.ndarray):
    padded = np.concatenate(([False], mask, [False])).astype(np.int8)
    d = np.diff(padded)
    return zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1)


def _hhmm(ts: int) -> str:
    return pd.Timestamp(ts, unit="s").strftime("%a %H:%M")