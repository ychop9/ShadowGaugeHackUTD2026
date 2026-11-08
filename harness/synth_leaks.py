from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

from engine.loader import iter_facilities, last_ts, load_dataset, series
from harness.sweep_leak_thresholds import ONSET_WINDOW_S, episode_starts, facility_frame

SETTINGS = [(-25, 80), (-20, 60), (-15, 40), (-12, 30)]   # (offset psi, gap bpd)
RAMP_H = [1, 3, 6, 12]
OFFSET_PEAK = [-30, -50, -70]                             # psi, applied at full ramp
GAP_PEAK = [60, 140, 200]                                 # bpd, applied at full ramp
DURATION_H = 24
PAD_S = 12 * 3600                                         # keep this clear of real labels
SITE_DAYS = [1, 2, 3]                                     # injection days after the first sample


def inject_leak(ds, item, onset, ramp_s, off_pk, gap_pk, duration_s):
    """Return a copy of ds with a synthetic leak on this facility's pipeline.
    Applied only where the pump is running, since the plan says a leak is
    invisible while the pump is off."""
    fac = item["facility"]
    pump_id, pipe_id = fac["pump"]["id"], fac["pipeline"]["id"]
    tel = ds.telemetry
    ts_all = tel.index.get_level_values("ts_unix").to_numpy()
    asset = tel.index.get_level_values("asset_id").to_numpy()
    metric = tel.index.get_level_values("metric").to_numpy()

    st = series(ds, pump_id, "status")
    run_ts = st.index[st.to_numpy() == 1].to_numpy()
    running = np.isin(ts_all, run_ts)

    in_win = (ts_all >= onset) & (ts_all < onset + duration_s)
    ramp = np.clip((ts_all - onset) / ramp_s, 0, 1)

    new = tel["value"].to_numpy(copy=True)
    p = (asset == pipe_id) & (metric == "pressure_psi") & in_win & running
    r = (asset == pipe_id) & (metric == "receive_flow_bpd") & in_win & running
    new[p] += off_pk * ramp[p]
    new[r] -= gap_pk * ramp[r]
    return dataclasses.replace(ds, telemetry=tel.assign(value=new))


def sites(ds, key_path: Path):
    """Injection sites: first five facilities, at fixed days, clear of labelled windows."""
    import json
    key = json.loads(key_path.read_text(encoding="utf-8")) if key_path.exists() else []
    t0 = int(ds.telemetry.index.get_level_values("ts_unix").min())
    facs = [it for it in iter_facilities(ds)][:5]
    for item in facs:
        fid = item["facility"]["id"]
        for day in SITE_DAYS:
            onset = t0 + day * 86400 + 2 * 3600
            clear = not any(
                k["facility"] == fid
                and k["onset_unix"] - PAD_S <= onset + DURATION_H * 3600
                and k["end_unix"] + PAD_S >= onset
                for k in key
            )
            if clear:
                yield item, onset


def run_grid(folder: Path) -> int:
    ds0 = load_dataset(folder)
    now = last_ts(ds0)
    key_path = folder / "answer_key.json"
    site_list = list(sites(ds0, key_path))

    print(f"{folder.name}: {len(site_list)} sites, "
          f"{len(RAMP_H) * len(OFFSET_PEAK) * len(GAP_PEAK)} shapes per site")
    print(f"{'offset':>7} {'gap':>5} | {'ramp h':>6} {'detect':>8} {'median lag h':>13} {'healthy eps':>12}")

    for t_off, t_gap in SETTINGS:
        for ramp_h in RAMP_H:
            hits, lags, healthy = 0, [], 0
            total = 0
            for item, onset in site_list:
                for op in OFFSET_PEAK:
                    for gp in GAP_PEAK:
                        total += 1
                        ds = inject_leak(ds0, item, onset, ramp_h * 3600, op, gp, DURATION_H * 3600)
                        ts, off, gap = facility_frame(ds, item, now)
                        flag = (off < t_off) & (gap > t_gap)

                        end = onset + DURATION_H * 3600
                        win = flag & (ts >= onset - ONSET_WINDOW_S) & (ts <= end)
                        first = np.flatnonzero(win)
                        if len(first):
                            hits += 1
                            lags.append((ts[first[0]] - onset) / 3600)

                        # Alarms well away from the injection window.
                        away = (ts < onset - PAD_S) | (ts > end + PAD_S)
                        healthy += len(episode_starts(flag & away))

            med = f"{np.median(lags):+.2f}" if lags else "n/a"
            print(f"{t_off:>7} {t_gap:>5} | {ramp_h:>6} {hits:>3}/{total:<4} {med:>13} {healthy:>12}",
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run_grid(Path(sys.argv[1])))