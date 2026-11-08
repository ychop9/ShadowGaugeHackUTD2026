from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_FILES = ("network.json", "ops.json", "telemetry.csv")


@dataclass(frozen=True)
class Dataset:
    name: str
    folder: Path
    network: dict
    ops: dict
    telemetry: pd.DataFrame  # index: (asset_id, metric, ts_unix); column: value


def load_dataset(folder: str | Path, cache_dir: str | Path = "cache") -> Dataset:
    folder = Path(folder)
    for name in REQUIRED_FILES:
        if not (folder / name).is_file():
            raise FileNotFoundError(f"{folder} is missing {name}")

    network = json.loads((folder / "network.json").read_text())
    ops = json.loads((folder / "ops.json").read_text())
    telemetry = _load_telemetry(folder / "telemetry.csv", Path(cache_dir))

    _validate(network, ops)
    return Dataset(folder.name, folder, network, ops, telemetry)


def _cache_path(csv: Path, cache_dir: Path) -> Path:
    st = csv.stat()
    key_src = f"{csv.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    key = hashlib.sha1(key_src.encode()).hexdigest()[:16]
    return cache_dir / f"telemetry_{key}.parquet"


def _load_telemetry(csv: Path, cache_dir: Path) -> pd.DataFrame:
    cache = _cache_path(csv, cache_dir)
    if cache.exists():
        return pd.read_parquet(cache)

    df = pd.read_csv(
        csv,
        usecols=["ts_unix", "asset_id", "metric", "value"],
        dtype={"ts_unix": "int64", "asset_id": "string", "metric": "string", "value": "float64"},
    )
    df = df.set_index(["asset_id", "metric", "ts_unix"]).sort_index()
    if not df.index.is_unique:
        raise ValueError(f"{csv.name} has duplicate (asset, metric, ts) rows")

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache)
    return df


def _validate(network: dict, ops: dict) -> None:
    for system in network["systems"]:
        sid = system["id"]
        fleet = ops["systems"].get(sid)
        if fleet is None:
            raise ValueError(f"ops.json has no entry for system {sid}")
        for fac in system["facilities"]:
            if fac["id"] not in fleet["facilities"]:
                raise ValueError(f"ops.json has no response/cycle for {fac['id']}")


def series(ds: Dataset, asset_id: str, metric: str, now: int | None = None) -> pd.Series:
    """Sensor series indexed by ts_unix, optionally sliced to ts_unix <= now."""
    s = ds.telemetry.loc[(asset_id, metric), "value"]
    if now is not None:
        s = s[s.index <= now]
    return s


def last_ts(ds: Dataset) -> int:
    return int(ds.telemetry.index.get_level_values("ts_unix").max())


def sample_interval_s(ds: Dataset) -> int:
    ts = pd.Series(ds.telemetry.index.get_level_values("ts_unix").unique()).sort_values()
    return int(ts.diff().median())


def iter_facilities(ds: Dataset):
    """Yields one dict per facility with its system, equipment and ops parameters."""
    for system in ds.network["systems"]:
        fleet = ds.ops["systems"][system["id"]]
        for fac in system["facilities"]:
            yield {
                "system": system,
                "facility": fac,
                "fleet_size": fleet["emergency_fleet_size"],
                "response_min": fleet["facilities"][fac["id"]]["response_min"],
                "cycle_min": fleet["facilities"][fac["id"]]["cycle_min"],
            }