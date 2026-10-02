"""Build clock-face and percentile timetables, and evaluate their punctuality."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import DIRECTIONS, hhmm_to_min, min_to_hhmmss
from .simulate import simulate


@dataclass
class Trip:
    trip_id: str
    direction: str
    stop_ids: list
    sched: np.ndarray        # absolute minutes: departure times, arrival at last stop

    @property
    def dep_min(self) -> float:
        return float(self.sched[0])

    @property
    def arr_min(self) -> float:
        return float(self.sched[-1])


def departure_times(cfg):
    t = cfg["timetable"]
    return list(range(hhmm_to_min(t["first_departure"]),
                      hhmm_to_min(t["last_departure"]) + 1,
                      int(t["headway_min"])))


def _nan_reduce(func, x, *args):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # never-served stops -> all-NaN columns
        return func(x, *args, axis=0)


def _clean_offsets(off):
    off = np.array(off, dtype=float)
    off[0] = 0.0
    for k in range(1, len(off)):
        if np.isnan(off[k]):
            off[k] = off[k - 1]
    return np.maximum.accumulate(np.round(off))       # whole minutes, never decreasing


def _event_offsets(m, dep, s):
    return simulate(m, dep, s.n, s.rng, s.rho).event_times() - dep


def build_timetable(cfg, models, s, kind, q=None):
    """kind = 'flat': one set of running times for all departures (the day's average).
    kind = 'percentile': each departure gets times at the q-th percentile of
    simulated journeys starting at that time."""
    deps = departure_times(cfg)
    trips = []
    for direction in DIRECTIONS:
        m = models[direction]
        if kind == "flat":
            per_dep = [_nan_reduce(np.nanmean, _event_offsets(m, d, s)) for d in deps]
            flat = _clean_offsets(_nan_reduce(np.nanmean, np.vstack(per_dep)))
        for i, d in enumerate(deps):
            if kind == "flat":
                off = flat
            else:
                off = _clean_offsets(_nan_reduce(np.nanquantile, _event_offsets(m, d, s), q))
            trips.append(Trip(f"{direction[0].upper()}{i + 1:02d}", direction,
                              m.stop_ids, d + off))
    return trips


def evaluate(trips, models, cfg, s) -> pd.DataFrame:
    """Simulate each trip against its schedule; punctuality at timing points."""
    p = cfg["punctuality"]
    early, late = p["early_limit_min"], p["late_limit_min"]
    rows = []
    for tr in trips:
        m = models[tr.direction]
        res = simulate(m, tr.dep_min, s.n, s.rng, s.rho, schedule=tr.sched)
        dev = res.event_times() - tr.sched
        last = len(tr.stop_ids) - 1
        for k in range(1, last + 1):
            if not m.timing[k]:
                continue
            d = dev[:, k]
            d = d[~np.isnan(d)]
            if k == last:
                on_time = d <= late                  # early arrival at the end is not a failure
            else:
                on_time = (d >= -early) & (d <= late)
            rows.append({
                "trip_id": tr.trip_id, "direction": tr.direction, "dep_min": tr.dep_min,
                "stop_id": tr.stop_ids[k], "stop_seq": k, "final_stop": k == last,
                "on_time": on_time.mean(), "mean_dev_min": d.mean(),
                "p95_dev_min": np.quantile(d, 0.95), "sched_min": tr.sched[k] - tr.dep_min,
            })
    return pd.DataFrame(rows)


def summarise(ev: pd.DataFrame, trips) -> dict:
    fin = ev[ev.final_stop]
    return {
        "on_time_timing_points": float(ev.on_time.mean()),
        "on_time_final_stop": float(fin.on_time.mean()),
        "mean_scheduled_end_to_end_min": float(np.mean([t.arr_min - t.dep_min for t in trips])),
        "worst_p95_lateness_final_min": float(fin.p95_dev_min.max()),
    }


def to_frame(trips) -> pd.DataFrame:
    rows = []
    for t in trips:
        row = {"trip_id": t.trip_id, "direction": t.direction}
        row.update({sid: min_to_hhmmss(x)[:5] for sid, x in zip(t.stop_ids, t.sched)})
        rows.append(row)
    return pd.DataFrame(rows)
