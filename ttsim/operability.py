"""Vehicle blocks, battery state of charge and drivers' hours checks.

Simplifications (state these in the README):
- Charging only at stops with charger = true, only during layovers,
  at a constant average rate (peak power x efficiency); no taper curve.
- Uses scheduled times; knock-on delays between trips are not simulated.
- One driver per vehicle block. Only a single break of >= 45 min resets
  driving time; the permitted 15 + 30 split break is not modelled.
  Trip duration (including dwell) is counted as driving - conservative.
- Energy uses the winter factor, i.e. this is a cold-weather check.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Vehicle:
    vid: int
    location: str
    free_at: float
    soc_kwh: float
    driving_since_break: float = 0.0
    min_soc_kwh: float = np.inf
    trips: list = field(default_factory=list)


def build_blocks(trips, cfg) -> dict:
    o = cfg["operations"]
    cap = o["battery_usable_kwh"]
    reserve = cap * o["reserve_fraction"]
    rate_kw = o["charge_power_kw"] * o["charge_efficiency"]
    energy = sum(s.distance_km for s in cfg.segments) * o["consumption_kwh_per_km"] * o["winter_factor"]
    if energy > cap - reserve:
        raise ValueError(f"One trip needs {energy:.0f} kWh but only {cap - reserve:.0f} kWh is "
                         "usable above reserve: not viable without en-route charging.")
    chargers = {s.id: s.charger for s in cfg.stops}

    fleet, flags = [], []
    for tr in sorted(trips, key=lambda t: t.dep_min):
        origin, dest = tr.stop_ids[0], tr.stop_ids[-1]
        best = None
        for v in fleet:
            layover = tr.dep_min - v.free_at
            if v.location != origin or layover < o["min_layover_min"]:
                continue
            soc = min(cap, v.soc_kwh + (rate_kw * layover / 60 if chargers[origin] else 0.0))
            if soc - energy < reserve:
                continue
            if best is None or v.free_at < best[0].free_at:     # longest-waiting vehicle first
                best = (v, soc, layover)
        if best is None:
            v, soc, layover = Vehicle(len(fleet) + 1, origin, tr.dep_min, cap), cap, np.inf
            fleet.append(v)
        else:
            v, soc, layover = best

        if layover >= o["min_break_min"]:
            v.driving_since_break = 0.0
        drive = tr.arr_min - tr.dep_min
        if v.driving_since_break + drive > o["max_driving_min"]:
            flags.append({"vehicle": v.vid, "trip_id": tr.trip_id, "dep_min": tr.dep_min,
                          "driving_before_trip_min": round(v.driving_since_break, 1),
                          "trip_min": round(drive, 1)})
            v.driving_since_break = 0.0   # assume a break/changeover is inserted; count breaches separately
        v.driving_since_break += drive
        v.soc_kwh = soc - energy
        v.min_soc_kwh = min(v.min_soc_kwh, v.soc_kwh)
        v.free_at, v.location = tr.arr_min, dest
        v.trips.append(tr.trip_id)

    blocks = pd.DataFrame([{"vehicle": v.vid, "n_trips": len(v.trips), "trips": " ".join(v.trips),
                            "min_soc_pct": round(100 * v.min_soc_kwh / cap, 1)} for v in fleet])
    return {"peak_vehicles": len(fleet), "blocks": blocks, "driver_flags": pd.DataFrame(flags)}
