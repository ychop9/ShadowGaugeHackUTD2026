"""HTTP API for the ShadowGauge console. Thin layer over `engine/`.

Run from the repo root:  uvicorn app.main:app --reload --port 8000
Any folder under data/ or test/ that holds network.json, ops.json and telemetry.csv is a dataset,
so the judging `test/` folder shows up with no code change.
"""
from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from app.auth import USERS_DB, LoginRequest, create_access_token, verify_password
from engine.dashboard import dashboard
from engine.events import analyze
from engine.loader import REQUIRED_FILES, Dataset, first_ts, last_ts, load_dataset, series

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = [ROOT / "data", ROOT / "test"]
CACHE_DIR = ROOT / "cache"

app = FastAPI(title="ShadowGauge API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _warm_up():
    """Load every dataset and compute its latest dashboard in the background, so switching
    datasets in the UI is instant. One at a time to keep memory low. A test/ folder added
    later is still picked up on first request."""
    def run():
        for name in discover():
            try:
                get_dashboard(name)
                timeline(name)
            except Exception as e:   # a broken folder must not stop the others
                print(f"warm-up skipped {name}: {e}")
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- datasets

def discover() -> dict[str, Path]:
    found = {}
    for base in SEARCH_DIRS:
        if not base.is_dir():
            continue
        for net in sorted(base.rglob("network.json")):
            folder = net.parent
            if all((folder / f).is_file() for f in REQUIRED_FILES):
                found[folder.name] = folder
    return found


@lru_cache(maxsize=8)
def _load(path: str, mtime_ns: int) -> Dataset:
    return load_dataset(path, cache_dir=CACHE_DIR)


def get_dataset(name: str) -> Dataset:
    folder = discover().get(name)
    if folder is None:
        raise HTTPException(404, f"No dataset named {name!r}")
    return _load(str(folder), (folder / "telemetry.csv").stat().st_mtime_ns)


@lru_cache(maxsize=64)
def _analysis(name: str, now: int, mtime_ns: int) -> dict:
    return analyze(get_dataset(name), now)


def _clamp_now(ds: Dataset, now: int | None) -> int:
    first, end = first_ts(ds), last_ts(ds)
    return end if now is None else max(first, min(end, now))


# ---------------------------------------------------------------- routes

@app.get("/")
def health():
    return {"status": "online", "datasets": list(discover())}


@app.post("/api/v1/auth/login")
def login(credentials: LoginRequest):
    user = USERS_DB.get(credentials.username)
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return {
        "access_token": create_access_token({"sub": user["username"]}),
        "token_type": "bearer",
        "user": {k: user[k] for k in ("username", "full_name", "role")},
    }


@app.get("/api/v1/datasets")
def list_datasets():
    """Every loadable dataset folder. Telemetry isn't parsed here, so this stays fast."""
    return [{"name": n, "path": str(p.relative_to(ROOT)),
             "has_answer_key": (p / "answer_key.json").is_file()}
            for n, p in discover().items()]


@app.get("/api/v1/datasets/{name}/network")
def network(name: str):
    """network.json + ops.json + the telemetry time range, for the map and the time slider."""
    ds = get_dataset(name)
    return {"network": ds.network, "ops": ds.ops,
            "time_range": {"start_unix": first_ts(ds), "end_unix": last_ts(ds)}}


@app.get("/api/v1/datasets/{name}/analysis")
def analysis(name: str, now: int | None = Query(None, description="ts_unix; default = last sample")):
    """Alerts (ongoing, in alerts-view order) and every event, with countdowns and plans.
    Pass `now` to time-travel: everything is computed only from readings up to then."""
    ds = get_dataset(name)
    folder = discover()[name]
    return _analysis(name, _clamp_now(ds, now), (folder / "telemetry.csv").stat().st_mtime_ns)


@lru_cache(maxsize=64)
def _dashboard(name: str, now: int, mtime_ns: int) -> dict:
    return dashboard(get_dataset(name), now)


@app.get("/api/v1/datasets/{name}/dashboard")
def get_dashboard(name: str, now: int | None = Query(None, description="ts_unix; default = last sample")):
    """Everything the main page needs: every facility's live readings (named as in the data
    files), detected issues with plans, trucks per system, and the alerts list.
    Pass an increasing `now` to replay the week."""
    ds = get_dataset(name)
    folder = discover()[name]
    return _dashboard(name, _clamp_now(ds, now), (folder / "telemetry.csv").stat().st_mtime_ns)


@app.get("/api/v1/datasets/{name}/series")
def get_series(name: str, asset_id: str, metric: str,
               start: int | None = None, end: int | None = None,
               max_points: int = Query(2000, ge=10, le=20000)):
    """One sensor over time as [[ts_unix, value], ...], evenly thinned to max_points."""
    ds = get_dataset(name)
    try:
        s = series(ds, asset_id, metric, end)
    except KeyError:
        raise HTTPException(404, f"No series {asset_id}/{metric}")
    if start is not None:
        s = s[s.index >= start]
    step = max(1, len(s) // max_points)
    s = s.iloc[::step]
    return {"asset_id": asset_id, "metric": metric,
            "points": [[int(t), float(v)] for t, v in s.items()]}


@lru_cache(maxsize=16)
def _timeline(name: str, mtime_ns: int) -> dict:
    ds = get_dataset(name)
    res = analyze(ds, last_ts(ds))
    return {"time_range": {"start_unix": first_ts(ds), "end_unix": last_ts(ds)},
            "events": [{"event_id": e["event_id"], "category": e["category"],
                        "facility_id": e["facility_id"], "onset_unix": e["onset_unix"],
                        "end_unix": e["end_unix"]} for e in res["events"]]}


@app.get("/api/v1/datasets/{name}/timeline")
def timeline(name: str):
    """Every event found in the whole recording (onset/end), for the replay slider's markers
    and the jump-to-next-event button. Navigation only: what the page shows at any moment
    still comes from /dashboard?now=, which uses readings up to that moment and nothing later."""
    get_dataset(name)
    folder = discover()[name]
    return _timeline(name, (folder / "telemetry.csv").stat().st_mtime_ns)
