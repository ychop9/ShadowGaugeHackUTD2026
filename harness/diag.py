"""Diagnostics for the harness failures. Read-only: prints, changes nothing.

Run from the project root:
    python -m harness.diag
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.detect import _running_frame, calibrate, detect_all
from engine.events import _prior_before, analyze
from engine.loader import iter_facilities, last_ts, load_dataset

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "history" / "full_week"
CACHE = ROOT / "cache"
SLOW_IDS = ["EVENT_1", "EVENT_2", "EVENT_10", "EVENT_16", "EVENT_17"]


def _t(ts: int) -> str:
    return pd.Timestamp(ts, unit="s").strftime("%a %m-%d %H:%M")


def slow_signals(ds, key, ours):
    items = {it["facility"]["id"]: it for it in iter_facilities(ds)}
    frames = {f: _running_frame(ds, it, None) for f, it in items.items()}
    cal = calibrate(ds, frames, None)
    w, rw = cal.window, np.sqrt(cal.window)

    for eid in SLOW_IDS:
        ref = key[eid]
        fac = ref["facility"]
        df = frames[fac]
        mean = df.rolling(w, min_periods=w).mean()
        z_gap = mean["gap"] / (cal.sd_gap / rw)
        z_p = (cal.p_offset - mean["p_off"]) / (cal.sd_p / rw)
        z_deg = (cal.r_ref - mean["ratio"]) / (cal.sd_ratio / rw)
        is_leak = ref["category"] == "pipeline_leak"
        z = np.minimum(z_gap, z_p) if is_leak else z_deg

        det = [e for e in ours if e["facility_id"] == fac and e["category"] == ref["category"]]
        det = min(det, key=lambda e: abs(e["onset_unix"] - ref["onset_unix"])) if det else None

        print(f"\n=== {eid} {ref['category']} {fac} ===")
        print(f"key onset {_t(ref['onset_unix'])}  key end {_t(ref['end_unix'])}")
        if det:
            print(f"ours onset {det['onset_ts']}  ours end {det['end_ts']}")
        print(f"gate z = {cal.z:.2f}   (above gate = still abnormal)")

        lo, hi = ref["onset_unix"] - 3600, ref["end_unix"] + 6 * 3600
        cols = {"z": z}
        if is_leak:
            cols.update({"z_gap": z_gap, "z_p": z_p})
        view = pd.DataFrame(cols)
        view = view[(view.index >= lo) & (view.index <= hi)]
        view = view.iloc[::w].round(2)
        view["time"] = [_t(t) for t in view.index]
        view["above"] = view["z"] > cal.z
        print(view.set_index("time").to_string())


def prior_check(ds, key):
    found = detect_all(ds, last_ts(ds))
    pf = sorted([e for e in found if e.category == "pump_failure"], key=lambda e: e.onset)
    onset = key["EVENT_18"]["onset_unix"]
    closed = [(e.onset, (e.end - e.onset) / 3600) for e in pf
              if e.end is not None and e.end < onset]

    print("\n=== EVENT_18 prior check ===")
    print(f"EVENT_18 onset {_t(onset)}")
    print("closed pump failures before it (onset, detected duration h):")
    for t, h in closed:
        print(f"  {_t(t)}  {h:.2f} h")
    if closed:
        print(f"median of these: {np.median([h for _, h in closed]):.3f} h")
    print(f"_prior_before(...): {_prior_before(pf, onset, 6 * 3600) / 3600:.3f} h")
    print("key durations of same failures (end - onset):")
    for eid, ref in key.items():
        if ref["category"] == "pump_failure" and ref.get("end_unix") and ref["end_unix"] < onset:
            print(f"  {eid} {(ref['end_unix'] - ref['onset_unix']) / 3600:.2f} h")


def main():
    ds = load_dataset(DATA, cache_dir=CACHE)
    key = {e["id"]: e for e in json.loads((DATA / "answer_key.json").read_text(encoding="utf-8"))}
    ours = analyze(ds)["events"]
    slow_signals(ds, key, ours)
    prior_check(ds, key)


if __name__ == "__main__":
    main()