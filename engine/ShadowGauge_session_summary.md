# ShadowGauge Backend: Session Summary

## 1. Goal

Build the Python engine for the Avon console. The engine detects pump failures, pump degradation, and pipeline leaks from sensor readings alone, forecasts shut-in time, and recommends the lowest-cost response with shared trucks. The app must work on a network it has never seen (`test/`, systems S6 to S11), with no answer key and no hardcoded IDs, prices, limits, or fleet sizes.

## 2. Environment

- Windows, PowerShell, Python 3.11, run from the repo root.
- Packages: pandas, pyarrow (required for the Parquet cache), fastapi, uvicorn, pytest.
- Repo layout: `engine/` (pure Python), `harness/` (scoring, reads the key), `api/` (not started), `web/` (frontend developer), `data/history/` (five dataset folders).

## 3. Data facts confirmed this session

| Fact | Evidence |
|---|---|
| Telemetry sample interval is 5 minutes | 195 rows per timestamp; 2,016 samples per week gives 393,120 rows |
| Facility inflow equals the sum of its wells' water | S1_FACILITY_A: 1002 + 798.7 + 599.1 = 2399.8 bpd |
| Pipeline pressure sits about 50 psi above disposal when healthy | S1_PIPELINE_A: 1100.3 psi vs 1050 psi disposal |
| Pump status 0 is normal cycling, not a fault | Pump off at 35.68% tank level, between the 70% start and 30% stop |
| Only status 2 means fault | Confirmed against the answer key's pump failures |
| Answer key is a flat list of 23 events | Fields: `id, category, facility, asset, system, onset, onset_unix, end, end_unix, status, reference_action` |
| Category strings | `pump_failure` (13), `pipeline_leak` (5), `pump_degradation` (5) |
| Cost math check | S1_WELL_C2 at 170 bbl/d and 600 mcf/d is $500/h at $60/bbl and $3/mcf; 3 h 55 min gives about $1,958 |
| `mock_test_2026-10-10T1530` is not independent | Its leak tables are identical to `full_week`'s |

## 4. Changes made, in order

1. **Environment:** installed pyarrow after the first Parquet cache error.
2. **Loader (`engine/loader.py`):** reads only the three runtime files, caches telemetry as Parquet keyed on file path, size, and mtime, and validates that every facility has an `ops.json` entry. `series()` slices to `now`.
3. **Harness (`harness/score.py`):** first used placeholder answer-key names; these were replaced after the real structure was printed. Later refactored into one shared `score()` function with labelled onset errors. A keyless mode (`run_engine_only`) prints engine output for folders with no key.
4. **Pump failure (`engine/detect.py`):** status-2 runs, `repair_end = onset + expected_repair_hours`. Passes 13/13 on full week and all snapshots with no false positives.
5. **Pump degradation (`engine/detect.py`):** went through several versions.
   - First version (fixed 0.985 and 0.995 gates, 48 h hinge back-dating): 5/5 matched, 3 false positives.
   - Diagnosis: the false positives were ramp-ups after restarts, and back-dating crossed pump-off gaps.
   - Attempt 1 (2-hour warm-up after each restart plus a segment-only back-dating limit): worse. It masked too much data.
   - Attempt 2 (mask 3 samples at each run edge): 5/5 with 3 false positives.
   - Attempt 3 (contiguous-span check on the rolling window): 4/5 with 1 false positive.
   - Attempt 4 (back-dating limited to the current running segment): 5/5, 0 false positives on all four folders.
   - Note: attempts 1 and 4 both used a segment restriction. Attempt 4 was kept because it passed; the earlier attempt also dropped the warm-up.
6. **Leak sweep (`harness/sweep_leak_thresholds.py`):** the plan's gate (−25 psi, 80 bpd) caught the five real leaks about 4.6 h late on average. Lower gates caught them earlier with no healthy alarms on the clean week. Found that the healthy count excludes labelled windows and that the sweep uses an unrealistic smoothing window.
7. **Synthetic leak grid (`harness/synth_grid.py leak`):** injected linear ramps and steps into healthy running stretches. Result: both-signal leaks were detected at 100% for ramps up to 6 h at the gates (3,3) through (6,6); (8,8) fell to 80%. Pressure-only and gap-only shapes were missed at every setting.
8. **Synthetic degradation grid (`harness/synth_grid.py degradation`):** with the fixed 0.985 gate, 12 h drops were detected at all sizes; 24 h at 3% detected 1 of 5 with 4 false alarms; 36 h at 3% detected 0 of 5 with 5 false alarms. The fixed gate does not generalize to slow drops.
9. **Removal of hardcoded numbers:** `engine/config.py` was dropped. The new `engine/calibrate.py` computes:
   - centers and spreads from each dataset's own healthy samples (median and MAD);
   - the smoothing and persistence window from the autocorrelation decorrelation length, capped at the repair window from `ops.json`;
   - gates as a z-score set so about one false episode is expected per dataset;
   - the back-dating window from the running segment.
10. **Leak detector moved to `engine/leak.py`:** calibrated gates, episodes ordered by time.
11. **Degradation rewritten in `engine/detect.py`:** calibrated baseline, leak-like sample removal using the dataset's gap distribution, ramp-up removal per run, and confidence from the normal CDF of the deviation.
12. **Import and cleanup fixes:** removed duplicate `_hinge_onset` and `_run_segment_ids` definitions, a self-calling `check_pump_failures`, and stray mid-file imports. Leak code removed from `detect.py`.
13. **Labelling fix:** the onset-error line now names its category. It had been printed under pump failure but belonged to degradation. The corrected pump-failure onset error is 0.00 hours on the snapshot runs.

## 5. Findings

### Pump failure
- Works on all folders. Detection reads only the status code and the repair time from `ops.json`, so there was little to fit.

### Pump degradation
- The fixed 0.985 gate fired on normal wander at slow drops and missed slow real drops. It should not be used.
- False positives on the real week came from ramp-up after restarts and from back-dating across pump-off gaps. The ramp-up is a real physical effect and is handled by the ramp mask.
- Back-dated onsets on the real week were close to the key's onset only after the segment limit was added.

### Pipeline leak
- The five real leaks are detected 3.75 to 7.75 hours after their key onset with the fixed gate. The pump was running for 41 to 58 steady samples before detection, so the lag is not explained by pump-off time. The first hypothesis (pump-off masking) was tested and rejected.
- The leak ramp is visible earlier: pressure offset starts at −15 to −20 psi and the flow gap at 40 to 60 bpd, and grows over 4 to 8 hours. The plan's gate (−25 psi and 80 bpd) is reached only after the leak is established.
- This is not the same as a proven general property. Five events from one generator cannot show that every network ramps this way.

### Synthetic grids
- The leak grid's lags are inflated. Even a 0-hour step gave a median lag of about +4 h, which is consistent with the injector starting at a fixed time when the pump is off, so the effect begins only at the next restart. This was **not yet confirmed** on the data. The fix (move onset to the first steady-running sample) is written but not applied.
- Degradation grid lags (about +3.75 h at every shape) show the same suspicion.
- Detection rates in both grids are still valid for shape. Lag numbers are not valid as detector latency until the injector is fixed.

### Calibration
- The snapshot at 10-09 03:30 has no run of `w` consecutive normal running samples for at least one pump, so `robust_scale` raises an error. The degradation code crashes instead of reporting that there is not enough data.

## 6. Known problems and open items

| # | Item | Status |
|---|---|---|
| 1 | `detect_pump_degradation` crashes on snapshot 10-09 03:30 (no finite rolling windows) | Fix proposed (skip facility when not calibratable); diagnostic command given; not confirmed |
| 2 | Injector onset not aligned to running samples in both grids | Fix proposed; not applied; lags not valid until applied |
| 3 | Calibrated leak detector not yet scored on the harness | Not run since the rewrite |
| 4 | Calibrated degradation detector not yet scored on the synthetic grid | Not run |
| 5 | Single-signal leaks (pressure-only, gap-only) missed | Assumed not physical; documented limit; not verified |
| 6 | Leak episodes can split or duplicate within one real leak | Not checked |
| 7 | `mock_test_*` folders have no key and are not independent of `full_week` | Accepted: use only for keyless runs |
| 8 | Degradation confidence and leak confidence use the normal CDF of the deviation | Definition needs agreement before showing operators |
| 9 | Harness tolerances (15 min, 2 h, 4 h) are hardcoded | Acceptable: harness-only, from the brief |
| 10 | Status codes 1 and 2, the 3600 seconds-per-hour conversion, and the 1/e decorrelation convention are literals | Acceptable: protocol, unit, or stated convention |

## 7. Principles adopted

- **Thresholds come from data.** Each gate is a centre and spread from the dataset's own healthy samples, with the z-score set by a false-alarm rule, not by the five labelled events.
- **The labelled events are for scoring only.** Tuning to them is overfitting, because the unseen network may differ.
- **Synthetic tests are a stand-in for the unseen network.** They test shapes we chose, so they show robustness only within those shapes.
- **Test each fix on all four folders.** A change that helps one event has to be checked against the rest.
- **Say which assumptions are untested.** Single-signal leaks, linear ramps, and the injector's timing are all assumptions.

## 8. Recommended next steps

1. Apply the crash fix in `detect_pump_degradation` and run the diagnostic on the snapshot to see which pumps lack calibration data.
2. Apply the onset-alignment fix to both synthetic grids, then rerun them. Only read lag values after this step.
3. Run the calibrated leak and degradation detectors through the harness on all four folders and record the new counts as the baseline.
4. Rerun the synthetic grids on the calibrated detectors and apply the decision rule: at least 95% detection for both-signal leaks at ramps up to 6 h and for degradation drops of 6% or more over 12 to 36 h, with zero false alarms on the clean week.
5. Check leak episodes for splitting within a single real leak.
6. Build the keyless engine path in `api/main.py` next, so the frontend can start on real data.
7. Before judging, load `test/`, check that no hardcoded values were needed, and time the cold load on the demo laptop.

## 9. Commands used

```powershell
# Harness, all four folders
foreach ($f in "full_week","snapshot_2026-10-08T1200","snapshot_2026-10-09T0330","snapshot_2026-10-10T0900") {
    python -m harness.score "data/history/$f"
}

# Keyless run on the rehearsal folder
python -m harness.score data/history/mock_test_2026-10-10T1530

# Answer-key categories
python -m harness.score data/history/full_week --categories

# Leak sweep
python -m harness.sweep_leak_thresholds data/history/full_week

# Synthetic grids
python -m harness.synth_grid leak data/history/full_week
python -m harness.synth_grid degradation data/history/full_week

# Degradation and leak diagnostics
python -m harness.diagnose_degradation data/history/full_week
python -m harness.diagnose_leaks data/history/full_week
python -m harness.diagnose_leak_ramp data/history/full_week
```
