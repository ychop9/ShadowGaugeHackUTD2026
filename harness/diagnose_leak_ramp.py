from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from engine.detect import detect_pipeline_leaks
from engine.loader import iter_facilities, last_ts, load_dataset, series

WINDOW_H = 12  # hours of each key leak to show


def main(folder: str) -> int:
    folder = Path(folder)
    ds = load_dataset(folder)
    key = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    now = last_ts(ds)
    found = detect_pipeline_leaks(ds, now=now)
    facs = {it["facility"]["id"]: it for it in iter_facilities(ds)}

    for k in key:
        if k["category"] != "pipeline_leak":
            continue
        item = facs[k["facility"]]
        fac = item["facility"]
        disposal = item["system"]["disposal_site"]["pressure_psi"]
        pump_id = fac["pump"]["id"]
        pipe_id = fac["pipeline"]["id"]

        status = series(ds, pump_id, "status", now)
        ts = status.index.to_numpy()
        flow = series(ds, pump_id, "flow_bpd", now).reindex(ts).to_numpy()
        recv = series(ds, pipe_id, "receive_flow_bpd", now).reindex(ts).to_numpy()
        pres = series(ds, pipe_id, "pressure_psi", now).reindex(ts).to_numpy()
        s = status.to_numpy()

        running = np.zeros(len(s), dtype=bool)
        running[1:] = (s[1:] == 1) & (s[:-1] == 1)

        df = pd.DataFrame(
            {"offset": pres - (disposal + 50), "gap": flow - recv, "running": running},
            index=pd.to_datetime(ts, unit="s"),
        )
        start = k["onset_unix"]
        stop = min(k["end_unix"], start + WINDOW_H * 3600)
        win = df[(df.index >= pd.to_datetime(start, unit="s"))
                 & (df.index <= pd.to_datetime(stop, unit="s"))]
        run = win[win["running"]]

        hourly = run.resample("1h").agg(
            n=("running", "size"),
            offset_mean=("offset", "mean"),
            offset_min=("offset", "min"),
            gap_mean=("gap", "mean"),
            gap_max=("gap", "max"),
        ).dropna(subset=["n"])
        hourly = hourly[hourly["n"] > 0]

        det = next((d for d in found if d.facility_id == k["facility"]
                    and d.onset >= start - 3600), None)
        print(f"\n{k['id']} {k['facility']} key onset {pd.to_datetime(start, unit='s')}"
              f" | gate: offset < -25 psi and gap > 80 bpd")
        if det is not None:
            print(f"   detected onset {pd.to_datetime(det.onset, unit='s')}")
        print(hourly.round(1).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))