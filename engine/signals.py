from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import Dataset, series

SMOOTH = 6  # samples in the rolling mean used for leak detection


def raw_pipeline_signals(ds: Dataset, item: dict, now: int | None = None):
    """Unsmoothed signals for one facility. Non-steady-running samples are NaN.

    Steady running means pump status is 1 now and on the previous sample.
    Returns ts, running, pressure, gap where gap = pump flow - pipeline receive flow.
    Pressure is raw: no disposal or +50 psi assumption is made here.
    """
    fac = item["facility"]
    pump_id, pipe_id = fac["pump"]["id"], fac["pipeline"]["id"]

    status_s = series(ds, pump_id, "status", now)
    ts = status_s.index.to_numpy()
    s = status_s.to_numpy()
    running = np.zeros(len(s), dtype=bool)
    running[1:] = (s[1:] == 1) & (s[:-1] == 1)

    flow = series(ds, pump_id, "flow_bpd", now).reindex(ts).to_numpy()
    recv = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()
    pres = series(ds, pipe_id, "pressure_psi", now).reindex(ts).to_numpy()

    pressure = np.where(running, pres, np.nan)
    gap = np.where(running, flow - recv, np.nan)
    return ts, running, pressure, gap


def smooth(x: np.ndarray) -> np.ndarray:
    return pd.Series(x).rolling(SMOOTH, min_periods=SMOOTH).mean().to_numpy()