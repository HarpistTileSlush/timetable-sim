"""Synthetic running-time observations for development and demos.

These are NOT real data. Replace or supplement them with ridden journeys
or Routes API estimates before drawing any conclusions.
"""
import numpy as np
import pandas as pd

from .config import DIRECTIONS

DEMO_DATES = {"weekday": "2026-10-05", "weekend": "2026-10-10"}


def generate(cfg, rng) -> pd.DataFrame:
    syn = cfg["synthetic"]
    n = int(syn["obs_per_cell"])
    frames = []
    for direction in DIRECTIONS:
        for seg in cfg.segments_for(direction):
            for day_type in ("weekday", "weekend"):
                factors = syn["congestion"][day_type]
                for band, start, end in cfg.bands:
                    f = 1 + seg.congestion_sensitivity * (factors[band] - 1)
                    median = seg.freeflow_min * f
                    sigma = syn["sigma"][band] * (0.5 + 0.5 * seg.congestion_sensitivity)
                    frames.append(pd.DataFrame({
                        "segment_id": seg.id,
                        "obs_date": DEMO_DATES[day_type],
                        "depart_min": rng.uniform(start, end, n),
                        "day_type": day_type,
                        "run_min": median * np.exp(sigma * rng.standard_normal(n)),
                        "source": "synthetic",
                    }))
    return pd.concat(frames, ignore_index=True)
