"""DuckDB storage and SQL fitting of segment running-time distributions."""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from .config import DIRECTIONS

OBS_COLUMNS = ["segment_id", "obs_date", "depart_min", "day_type", "run_min", "source"]

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS bands (band VARCHAR, start_min INTEGER, end_min INTEGER)",
    """CREATE TABLE IF NOT EXISTS observations (
           segment_id VARCHAR, obs_date DATE, depart_min DOUBLE,
           day_type VARCHAR, run_min DOUBLE, source VARCHAR)""",
]

# Assign each observation to a time band with a range join, then fit a
# lognormal (mean and sd of log running time) per segment / day type / band.
BANDED_CTE = """
WITH banded AS (
    SELECT o.segment_id, o.day_type, b.band, ln(o.run_min) AS lr
    FROM observations AS o
    JOIN bands AS b
      ON CAST(floor(o.depart_min) AS INTEGER) % 1440 >= b.start_min
     AND CAST(floor(o.depart_min) AS INTEGER) % 1440 <  b.end_min
    WHERE list_contains(?, o.source)
)
"""
CELL_SQL = BANDED_CTE + """
SELECT segment_id, day_type, band, count(*) AS n, avg(lr) AS mu, stddev_samp(lr) AS sigma
FROM banded GROUP BY segment_id, day_type, band
"""
POOLED_SQL = BANDED_CTE + """
SELECT segment_id, day_type, count(*) AS n, avg(lr) AS mu, stddev_samp(lr) AS sigma
FROM banded GROUP BY segment_id, day_type
"""


def connect(path=":memory:"):
    con = duckdb.connect(str(path))
    for stmt in SCHEMA:
        con.execute(stmt)
    return con


def load_bands(con, cfg):
    con.execute("DELETE FROM bands")
    con.executemany("INSERT INTO bands VALUES (?, ?, ?)", [list(b) for b in cfg.bands])


def add_observations(con, df: pd.DataFrame):
    missing = set(OBS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Observations missing columns: {sorted(missing)}")
    obs = df[OBS_COLUMNS].copy()
    obs["obs_date"] = pd.to_datetime(obs["obs_date"]).dt.date
    obs["depart_min"] = obs["depart_min"].astype(float)
    obs["run_min"] = obs["run_min"].astype(float)
    con.register("incoming", obs)
    con.execute("INSERT INTO observations SELECT * FROM incoming WHERE run_min > 0")
    con.unregister("incoming")


def fit_params(con, cfg, sources, min_n=5, sigma_floor=0.02):
    """Return {(segment_id, day_type): (mu[bands], sigma[bands])}.

    Bands with fewer than min_n observations fall back to the pooled fit
    for that segment and day type.
    """
    sources = list(sources)
    cells = con.execute(CELL_SQL, [sources]).df()
    pooled = con.execute(POOLED_SQL, [sources]).df()
    band_names = [b[0] for b in cfg.bands]
    seg_ids = {s.id for d in DIRECTIONS for s in cfg.segments_for(d)}
    params = {}
    for seg in seg_ids:
        for day_type in ("weekday", "weekend"):
            p = pooled[(pooled.segment_id == seg) & (pooled.day_type == day_type)]
            if p.empty:
                continue
            mu = np.full(len(band_names), float(p["mu"].iloc[0]))
            sg = np.full(len(band_names), float(np.nan_to_num(p["sigma"].iloc[0], nan=sigma_floor)))
            c = cells[(cells.segment_id == seg) & (cells.day_type == day_type)]
            for _, r in c.iterrows():
                if r["n"] >= min_n:
                    i = band_names.index(r["band"])
                    mu[i], sg[i] = r["mu"], r["sigma"]
            params[(seg, day_type)] = (mu, np.maximum(sg, sigma_floor))
    return params
