from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from engine.loader import iter_facilities, last_ts, load_dataset, series

SWEEP = [(-25, 80), (-20, 60), (-15, 40), (-12, 30)]  # (offset psi, gap bpd)
SMOOTH = 6                 # rolling mean over running samples
EXCLUDE_PAD_S = 6 * 3600   # padding around labelled windows for the filtered healthy count
ONSET_WINDOW_S = 2 * 3600  # a flag this close before onset still counts as a hit


def facility_frame(ds, item, now):
    fac, system = item["facility"], item["system"]
    pump_id, pipe_id = fac["pump"]["id"], fac["pipeline"]["id"]
    disposal = system["disposal_site"]["pressure_psi"]

    status = series(ds, pump_id, "status", now)
    ts = status.index.to_numpy()
    s = status.to_numpy()
    running = np.zeros(len(s), dtype=bool)
    running[1:] = (s[1:] == 1) & (s[:-1] == 1)

    flow = series(ds, pump_id, "flow_bpd", now).reindex(ts).to_numpy()
    recv = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()
    pres = series(ds, pipe_id, "pressure_psi", now).reindex(ts).to_numpy()

    df = pd.DataFrame({
        "offset": np.where(running, pres - (disposal + 50), np.nan),
        "gap": np.where(running, flow - recv, np.nan),
    }, index=ts)
    sm = df.rolling(SMOOTH, min_periods=SMOOTH).mean()
    return ts, sm["offset"].to_numpy(), sm["gap"].to_numpy()


def episode_starts(mask: np.ndarray) -> np.ndarray:
    return np.flatnonzero(mask & ~np.concatenate(([False], mask[:-1])))


def load_key(key_folder: Path, now: int) -> list[dict]:
    path = key_folder / "answer_key.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    key = json.loads(path.read_text(encoding="utf-8"))
    # Only labels that had started by the cut-off count as labels for this run.
    return [k for k in key if k["onset_unix"] <= now]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m harness.sweep_leak_thresholds <folder> [key_folder]")
        return 2

    folder = Path(argv[1])
    key_folder = Path(argv[2]) if len(argv) > 2 else folder

    ds = load_dataset(folder)
    now = last_ts(ds)
    key = load_key(key_folder, now)
    leaks = [k for k in key if k["category"] == "pipeline_leak"]

    print(f"{folder.name} (key: {key_folder.name}), {len(leaks)} labelled leaks at now={now}")
    print(f"{'offset':>7} {'gap':>5} | {'hit':>5} {'signed lag h':>30} | "
          f"{'raw episodes':>12} {'healthy':>8}")

    for t_off, t_gap in SWEEP:
        hit, lags = 0, []
        raw, healthy = 0, 0

        for item in iter_facilities(ds):
            fac_id = item["facility"]["id"]
            ts, off, gap = facility_frame(ds, item, now)
            flag = (off < t_off) & (gap > t_gap)

            # Raw: every flagged episode on this facility, no exclusion.
            raw += len(episode_starts(flag))

            # Healthy: flagged episodes outside every labelled window (padded).
            excl = np.zeros(len(ts), dtype=bool)
            for k in key:
                if k["facility"] == fac_id:
                    excl |= (ts >= k["onset_unix"] - EXCLUDE_PAD_S) & (ts <= k["end_unix"] + EXCLUDE_PAD_S)
            healthy += len(episode_starts(flag & ~excl))

            # Hits: for each labelled leak here, the first flag in its window.
            for k in leaks:
                if k["facility"] != fac_id:
                    continue
                win = flag & (ts >= k["onset_unix"] - ONSET_WINDOW_S) & (ts <= k["end_unix"])
                first = np.flatnonzero(win)
                if len(first):
                    hit += 1
                    lags.append((ts[first[0]] - k["onset_unix"]) / 3600)

        if lags:
            lag_txt = f"mean {np.mean(lags):+.2f} [{min(lags):+.2f}, {max(lags):+.2f}]"
        else:
            lag_txt = "n/a"
        print(f"{t_off:>7} {t_gap:>5} | {hit:>2}/{len(leaks):<2} {lag_txt:>30} | "
              f"{raw:>12} {healthy:>8}", flush=True)

    print("\nraw = all flagged episodes, real leaks included.")
    print("healthy = flagged episodes outside labelled windows (padded), the optimistic count.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))