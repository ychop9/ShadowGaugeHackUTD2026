from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

from engine.detect import detect_pump_degradation
from engine.leak import calibrate_leak_baseline, episode_starts, leak_flags
from engine.loader import iter_facilities, last_ts, load_dataset
from engine.signals import raw_pipeline_signals, smooth

LEAK_SETTINGS = [(3, 3), (4, 4), (5, 4.5), (6, 6), (8, 8)]   # (k_pressure, k_gap) in noise units
LEAK_RAMP_H = [0, 1, 3, 6, 12]                               # 0 = step
LEAK_PEAKS = [(-30, 0), (-50, 0), (0, 60), (0, 140), (-30, 60), (-50, 140)]  # (psi, bpd)
LEAK_DUR_H = 24
ONSET_WIN_H = 2

DEG_SHAPES = [(h, d) for h in (12, 24, 36) for d in (0.03, 0.06, 0.12)]  # (hours, drop at end)
DEG_TOL_S = 4 * 3600

PAD_H = 12


def load_key(folder: Path) -> list[dict]:
    path = folder / "answer_key.json"
    if not path.is_file():
        return []   # test networks have no key; nothing is excluded
    return json.loads(path.read_text(encoding="utf-8"))


def labelled(key, fid, lo, hi, pad) -> bool:
    return any(k["facility"] == fid and k["onset_unix"] - pad <= hi and k["end_unix"] + pad >= lo
               for k in key)


def make_sites(ds, key, dur_s, pad_s):
    """One injection per facility, on a day chosen by its index, skipping labelled windows."""
    t0 = int(ds.telemetry.index.get_level_values("ts_unix").min())
    sites = []
    for n, item in enumerate(iter_facilities(ds)):
        fid = item["facility"]["id"]
        onset = t0 + (1 + n % 4) * 86400 + 2 * 3600
        if labelled(key, fid, onset, onset + dur_s, pad_s):
            continue
        sites.append((item, onset))
    return sites


def inject_leak(p, g, ts, running, onset, dur_s, ramp_s, off_pk, gap_pk):
    """Add a leak to raw signals. Applied only while the pump is steady-running,
    since the plan says a leak is invisible while the pump is off."""
    active = running & (ts >= onset) & (ts < onset + dur_s)
    ramp = np.clip((ts - onset) / ramp_s, 0, 1) if ramp_s > 0 else np.ones(len(ts))
    p2, g2 = p.copy(), g.copy()
    p2[active] += off_pk * ramp[active]
    g2[active] += gap_pk * ramp[active]
    return p2, g2


def leak_grid(folder: Path) -> int:
    ds = load_dataset(folder)
    now = last_ts(ds)
    key = load_key(folder)
    base = calibrate_leak_baseline(ds, now)
    sites = make_sites(ds, key, LEAK_DUR_H * 3600, PAD_H * 3600)

    clean = {}
    for item in iter_facilities(ds):
        fid = item["facility"]["id"]
        ts, running, p, g = raw_pipeline_signals(ds, item, now)
        clean[fid] = (ts, running, p, g)

    print(f"{folder.name}: {len(sites)} injection sites, baselines calibrated per facility")
    print("\nHealthy episodes on the clean week (labelled windows excluded, padded):")
    healthy = {s: 0 for s in LEAK_SETTINGS}
    for fid, (ts, running, p, g) in clean.items():
        sp, sg = smooth(p), smooth(g)
        excl = np.zeros(len(ts), dtype=bool)
        for k in key:
            if k["facility"] == fid:
                excl |= (ts >= k["onset_unix"] - PAD_H * 3600) & (ts <= k["end_unix"] + PAD_H * 3600)
        for s in LEAK_SETTINGS:
            healthy[s] += len(episode_starts(leak_flags(sp, sg, base[fid], *s) & ~excl))
    for s in LEAK_SETTINGS:
        print(f"  k_p={s[0]:<4} k_g={s[1]:<4} healthy episodes: {healthy[s]}")

    # results[(setting, ramp_h, peak)] -> list of lag hours, or None for a miss
    results: dict = {}
    for ramp_h in LEAK_RAMP_H:
        for peak in LEAK_PEAKS:
            for s in LEAK_SETTINGS:
                results[(s, ramp_h, peak)] = []
            for item, onset in sites:
                fid = item["facility"]["id"]
                ts, running, p, g = clean[fid]
                p2, g2 = inject_leak(p, g, ts, running, onset, LEAK_DUR_H * 3600,
                                     ramp_h * 3600, *peak)
                sp, sg = smooth(p2), smooth(g2)
                for s in LEAK_SETTINGS:
                    flags = leak_flags(sp, sg, base[fid], *s)
                    win = flags & (ts >= onset - ONSET_WIN_H * 3600) & (ts <= onset + LEAK_DUR_H * 3600)
                    idx = np.flatnonzero(win)
                    results[(s, ramp_h, peak)].append(
                        (ts[idx[0]] - onset) / 3600 if len(idx) else None)

    print("\nDetection rate by ramp (all peak shapes, all sites), median lag in hours:")
    print(f"{'k_p':>4} {'k_g':>4} | " + " | ".join(f"ramp {r:>2}h" for r in LEAK_RAMP_H))
    for s in LEAK_SETTINGS:
        cells = []
        for r in LEAK_RAMP_H:
            lags, total = [], 0
            for peak in LEAK_PEAKS:
                for lag in results[(s, r, peak)]:
                    total += 1
                    if lag is not None:
                        lags.append(lag)
            med = f"{np.median(lags):+.1f}" if lags else "n/a"
            cells.append(f"{len(lags) / total:5.0%} {med:>5}")
        print(f"{s[0]:>4} {s[1]:>4} | " + " | ".join(cells))

    print("\nDetection rate by shape family (all ramps, all sites):")
    families = {"both": [(-30, 60), (-50, 140)],
                "pressure-only": [(-30, 0), (-50, 0)],
                "gap-only": [(0, 60), (0, 140)]}
    print(f"{'k_p':>4} {'k_g':>4} | " + " | ".join(f"{name:>13}" for name in families))
    for s in LEAK_SETTINGS:
        cells = []
        for name, peaks in families.items():
            hits = total = 0
            for r in LEAK_RAMP_H:
                for peak in peaks:
                    for lag in results[(s, r, peak)]:
                        total += 1
                        hits += lag is not None
            cells.append(f"{hits / total:>13.0%}")
        print(f"{s[0]:>4} {s[1]:>4} | " + " | ".join(cells))
    return 0


def inject_flow_drops(ds, plans, drop_end, dur_s):
    """Linear decline of pump flow after each onset, to drop_end at dur_s, on a copy of ds."""
    tel = ds.telemetry
    ts_all = tel.index.get_level_values("ts_unix").to_numpy()
    asset = tel.index.get_level_values("asset_id").to_numpy()
    metric = tel.index.get_level_values("metric").to_numpy()
    vals = tel["value"].to_numpy(copy=True)
    for pump_id, onset in plans:
        m = (asset == pump_id) & (metric == "flow_bpd") & (ts_all >= onset) & (ts_all < onset + dur_s)
        frac = (ts_all[m] - onset) / dur_s
        vals[m] *= 1 - drop_end * frac
    return dataclasses.replace(ds, telemetry=tel.assign(value=vals))


def degradation_grid(folder: Path) -> int:
    ds = load_dataset(folder)
    now = last_ts(ds)
    key = load_key(folder)
    sites = make_sites(ds, key, 36 * 3600, PAD_H * 3600)
    plans = [(item["facility"]["pump"]["id"], onset) for item, onset in sites]

    print(f"{folder.name}: {len(sites)} injection sites, one per facility")
    print(f"{'dur h':>6} {'drop':>5} | {'hit':>7} {'median lag h':>13} {'false':>6}")
    for dur_h, drop in DEG_SHAPES:
        ds2 = inject_flow_drops(ds, plans, drop, dur_h * 3600)
        found = detect_pump_degradation(ds2, now=now)

        hits, lags = 0, []
        for item, onset in sites:
            fid = item["facility"]["id"]
            m = [d for d in found if d.facility_id == fid and abs(d.onset - onset) <= DEG_TOL_S]
            if m:
                hits += 1
                lags.append((min(m, key=lambda d: abs(d.onset - onset)).onset - onset) / 3600)

        false = 0
        for d in found:
            near_site = any(it["facility"]["id"] == d.facility_id and abs(d.onset - o) <= DEG_TOL_S
                            for it, o in sites)
            if not near_site and not labelled(key, d.facility_id, d.onset, d.onset, PAD_H * 3600):
                false += 1

        med = f"{np.median(lags):+.2f}" if lags else "n/a"
        print(f"{dur_h:>6} {drop:>5.0%} | {hits:>3}/{len(sites):<3} {med:>13} {false:>6}", flush=True)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("leak", "degradation"):
        print("usage: python -m harness.synth_grid leak|degradation <folder>")
        return 2
    folder = Path(argv[2])
    return leak_grid(folder) if argv[1] == "leak" else degradation_grid(folder)


if __name__ == "__main__":
    sys.exit(main(sys.argv))