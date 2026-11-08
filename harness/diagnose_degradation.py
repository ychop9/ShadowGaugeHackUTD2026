from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine.detect import detect_pump_degradation
from engine.loader import iter_facilities, last_ts, load_dataset, series

TOL_S = 4 * 3600
CONTEXT_S = 24 * 3600


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def main(folder: str) -> int:
    folder = Path(folder)
    ds = load_dataset(folder)
    key = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    now = last_ts(ds)
    facs = {it["facility"]["id"]: it["facility"] for it in iter_facilities(ds)}
    found = detect_pump_degradation(ds, now=now)

    matched = set()
    for i, d in enumerate(found):
        for k in key:
            if (k["category"] == "pump_degradation" and k["facility"] == d.facility_id
                    and abs(d.onset - k["onset_unix"]) <= TOL_S):
                matched.add(i)

    for i, d in enumerate(found):
        if i in matched:
            continue
        print(f"\nFALSE {d.facility_id} onset={iso(d.onset)} "
              f"detected={iso(d.detected)} drop={d.drop_pct:.2f}%")

        near = [k for k in key
                if k["facility"] == d.facility_id
                and k["onset_unix"] < d.detected + CONTEXT_S
                and k["end_unix"] > d.onset - CONTEXT_S]
        for k in near:
            print(f"   nearby key: {k['category']} {k['id']} "
                  f"{iso(k['onset_unix'])} -> {iso(k['end_unix'])} ({k['status']})")
        if not near:
            print("   no key event of any category within 24 h")

        fac = facs[d.facility_id]
        pump = fac["pump"]
        flow = series(ds, pump["id"], "flow_bpd", now)
        status = series(ds, pump["id"], "status", now)
        df = pd.DataFrame({"flow": flow, "status": status})
        df.index = pd.to_datetime(df.index, unit="s")
        lo = pd.to_datetime(d.onset - 6 * 3600, unit="s")
        hi = pd.to_datetime(d.detected + 6 * 3600, unit="s")
        win = df.loc[lo:hi].copy()
        win["ratio"] = win["flow"] / pump["max_flow_bpd"]
        hourly = win.resample("1h").agg({"ratio": "mean", "status": "max"})
        print("   hourly profile (UTC):")
        print(hourly.round(4).to_string(header=["ratio", "status_max"]))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))