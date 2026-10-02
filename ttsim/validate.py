"""Turn journeys you have ridden into observations, and check model calibration."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import DIRECTIONS, hhmm_to_min
from .db import OBS_COLUMNS


def journeys_to_observations(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Columns: journey_id, date, day_type, stop_id, arrival_time, departure_time
    (HH:MM; leave blank if not applicable). List only stops actually called at,
    in travel order."""
    stops = {s.id: s for s in cfg.stops}
    valid = {seg.id for d in DIRECTIONS for seg in cfg.segments_for(d)}
    df = df.fillna("")
    rows, skipped = [], 0
    for _, g in df.groupby("journey_id", sort=False):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            seg_id = f"{a['stop_id']}>{b['stop_id']}"
            if seg_id not in valid:
                skipped += 1          # leg spans an unserved optional stop
                continue
            dep = hhmm_to_min(a["departure_time"] or a["arrival_time"])
            arr = hhmm_to_min(b["arrival_time"] or b["departure_time"])
            run = (arr - dep) % 1440
            if stops[b["stop_id"]].optional:
                run -= stops[b["stop_id"]].detour_s / 60   # the model adds detour separately
            if run <= 0:
                continue
            rows.append({"segment_id": seg_id, "obs_date": a["date"], "depart_min": dep,
                         "day_type": a["day_type"], "run_min": run, "source": "observed"})
    if skipped:
        print(f"Skipped {skipped} legs that span an unserved optional stop.")
    return pd.DataFrame(rows, columns=OBS_COLUMNS)


def calibration(obs: pd.DataFrame, params, cfg) -> pd.DataFrame:
    """Where does each observed run time fall in the model's distribution?
    A well-calibrated model gives percentiles spread roughly evenly 0-1."""
    starts = np.array([b[1] for b in cfg.bands])
    rows = []
    for r in obs.itertuples(index=False):
        key = (r.segment_id, r.day_type)
        if key not in params:
            continue
        mu, sg = params[key]
        b = np.searchsorted(starts, int(r.depart_min) % 1440, side="right") - 1
        z = (math.log(r.run_min) - mu[b]) / sg[b]
        rows.append({"segment_id": r.segment_id, "depart_min": r.depart_min,
                     "run_min": round(r.run_min, 1), "model_median_min": round(math.exp(mu[b]), 1),
                     "percentile_in_model": 0.5 * (1 + math.erf(z / math.sqrt(2)))})
    return pd.DataFrame(rows)
