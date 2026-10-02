"""Monte Carlo simulation of individual coach journeys."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SimSettings:
    n: int
    rho: float
    rng: np.random.Generator


@dataclass
class RouteModel:
    direction: str
    stop_ids: list
    optional: np.ndarray
    timing: np.ndarray
    serve_p: np.ndarray
    dwell_median_min: np.ndarray
    dwell_sigma: np.ndarray
    detour_min: np.ndarray
    seg_mu: np.ndarray        # (n_segments, n_bands), log minutes
    seg_sigma: np.ndarray
    band_starts: np.ndarray
    distance_km: float

    def band_index(self, t):
        return np.searchsorted(self.band_starts, np.mod(t, 1440), side="right") - 1


@dataclass
class SimResult:
    arr: np.ndarray           # (n, K) arrival times, NaN where stop not served
    dep: np.ndarray           # (n, K) departure times
    served: np.ndarray

    def event_times(self):
        """Departure at intermediate stops, arrival at the final stop."""
        ev = self.dep.copy()
        ev[:, -1] = self.arr[:, -1]
        return ev


def build_route_model(cfg, params, direction, day_type) -> RouteModel:
    stops = cfg.stops_for(direction)
    segs = cfg.segments_for(direction)
    mult = cfg["season_multiplier"][cfg["simulation"]["season"]]
    mus, sigmas = [], []
    for seg in segs:
        key = (seg.id, day_type)
        if key not in params:
            raise KeyError(f"No running-time data for {seg.id} ({day_type}). "
                           "Add observations or include 'synthetic' in --sources.")
        mus.append(params[key][0])
        sigmas.append(params[key][1])
    serve_p = np.array([min(1.0, s.serve_prob.get(day_type, 0.0) * mult) if s.optional else 1.0
                        for s in stops])
    return RouteModel(
        direction=direction,
        stop_ids=[s.id for s in stops],
        optional=np.array([s.optional for s in stops]),
        timing=np.array([s.timing_point for s in stops]),
        serve_p=serve_p,
        dwell_median_min=np.array([s.dwell_median_s / 60 for s in stops]),
        dwell_sigma=np.array([s.dwell_sigma for s in stops]),
        detour_min=np.array([s.detour_s / 60 for s in stops]),
        seg_mu=np.vstack(mus),
        seg_sigma=np.vstack(sigmas),
        band_starts=np.array([b[1] for b in cfg.bands]),
        distance_km=sum(s.distance_km for s in segs),
    )


def simulate(m: RouteModel, dep_min, n, rng, rho=0.5, schedule=None) -> SimResult:
    """Simulate n journeys departing at dep_min.

    - Optional stops are served with probability serve_p (demand-responsive).
    - Serving a stop adds its detour time and a lognormal dwell.
    - Running times are drawn from the band the coach is in *when it reaches*
      each segment, so a late-running coach can drift into the peak.
    - A shared per-journey factor (rho) correlates traffic across segments.
    - If a schedule is given, coaches may not depart timing points early.
    """
    K = len(m.stop_ids)
    served = np.ones((n, K), dtype=bool)
    served[:, m.optional] = rng.random((n, int(m.optional.sum()))) < m.serve_p[m.optional]

    arr = np.full((n, K), np.nan)
    dep = np.full((n, K), np.nan)
    t = np.full(n, float(dep_min))
    arr[:, 0] = t
    dep[:, 0] = t
    z_day = rng.standard_normal(n)
    idio = np.sqrt(1.0 - rho ** 2)

    for k in range(K - 1):
        nxt = k + 1
        b = m.band_index(t)
        z = rho * z_day + idio * rng.standard_normal(n)
        run = np.exp(m.seg_mu[k, b] + m.seg_sigma[k, b] * z)
        t = t + run + served[:, nxt] * m.detour_min[nxt]
        arr[:, nxt] = np.where(served[:, nxt], t, np.nan)
        if nxt == K - 1:
            break
        if m.dwell_median_min[nxt] > 0:
            dwell = m.dwell_median_min[nxt] * np.exp(m.dwell_sigma[nxt] * rng.standard_normal(n))
            t = t + served[:, nxt] * dwell
        if schedule is not None and m.timing[nxt]:
            t = np.maximum(t, schedule[nxt])
        dep[:, nxt] = np.where(served[:, nxt], t, np.nan)

    return SimResult(arr, dep, served)
