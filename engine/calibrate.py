from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
MAD_TO_SIGMA = 1 / _N.inv_cdf(0.75)   # constant for a normal distribution


@dataclass(frozen=True)
class Scale:
    center: float
    sigma: float
    n: int


def robust_scale(x: np.ndarray) -> Scale:
    x = x[np.isfinite(x)]
    if x.size == 0:
        raise ValueError("no finite samples to calibrate on")
    c = float(np.median(x))
    s = float(MAD_TO_SIGMA * np.median(np.abs(x - c)))
    if s <= 0:
        raise ValueError("zero spread in healthy samples; cannot calibrate")
    return Scale(c, s, int(x.size))


def sample_interval_s(ts: np.ndarray) -> int:
    return int(np.median(np.diff(ts)))


def steps(seconds: float, interval_s: int) -> int:
    return max(1, round(seconds / interval_s))


def decorrelation_steps(x: np.ndarray, max_steps: int) -> int:
    """First lag where autocorrelation falls below 1/e, searched up to max_steps.
    Averaging over this many samples gives roughly independent windows."""
    x = x[np.isfinite(x)]
    x = x - x.mean()
    var = float(np.dot(x, x))
    if var <= 0:
        return 1
    for k in range(1, max_steps + 1):
        if np.dot(x[:-k], x[k:]) / var < 1 / np.e:
            return k
    return max_steps


def gate_z(n_independent: float) -> float:
    """One-sided z with about one expected false episode across n_independent windows."""
    if n_independent < 2:
        raise ValueError("too little healthy data to set a gate")
    return _N.inv_cdf(1 - 1 / n_independent)


def rolling_mean(x: np.ndarray, w: int) -> np.ndarray:
    """Mean over w consecutive samples; NaN if any of them is NaN."""
    return pd.Series(x).rolling(w, min_periods=w).mean().to_numpy()