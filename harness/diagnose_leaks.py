from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from engine.detect import detect_pipeline_leaks
from engine.loader import iter_facilities, last_ts, load_dataset, series


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def main(folder: str) -> int:
    folder = Path(folder)
    ds = load_dataset(folder)
    key = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    now = last_ts(ds)
    found = detect_pipeline_leaks(ds, now=now)
    facs = {it["facility"]["id"]: it["facility"] for it in iter_facilities(ds)}

    for k in key:
        if k["category"] != "pipeline_leak":
            continue
        pump_id = facs[k["facility"]]["pump"]["id"]
        status = series(ds, pump_id, "status", now)
        window = status[(status.index >= k["onset_unix"]) & (status.index <= k["end_unix"])]
        running_pct = 100 * (window == 1).mean() if len(window) else float("nan")

        same = [d for d in found if d.facility_id == k["facility"]]
        near = min(same, key=lambda d: abs(d.onset - k["onset_unix"]), default=None)

        print(f"\n{k['id']} {k['facility']} key {iso(k['onset_unix'])} -> {iso(k['end_unix'])}"
              f" | pump running {running_pct:.0f}% of window")
        if near is None:
            print("   no detection on this facility")
            continue
        lag_h = (near.onset - k["onset_unix"]) / 3600
        between = status[(status.index >= k["onset_unix"]) & (status.index < near.onset)]
        running_between = int((between == 1).sum())
        print(f"   nearest detection {iso(near.onset)} lag {lag_h:+.2f} h"
              f" | running samples before detection: {running_between}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))