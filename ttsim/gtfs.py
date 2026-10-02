"""Export a timetable as a minimal GTFS feed (the format journey planners ingest)."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from .config import min_to_hhmmss

WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def export_gtfs(trips, cfg, outdir, service_start="20261101", service_end="20270430"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    r = cfg["route"]
    if any(s.lat == 0 and s.lon == 0 for s in cfg.stops):
        print("Warning: placeholder (0, 0) coordinates - fill from NaPTAN before publishing.")
    by_id = {s.id: s for s in cfg.stops}
    day_type = cfg["timetable"]["day_type"]
    days = [1, 1, 1, 1, 1, 0, 0] if day_type == "weekday" else [0, 0, 0, 0, 0, 1, 1]
    service_id = day_type.upper()

    stop_times = []
    for t in trips:
        for seq, (sid, time) in enumerate(zip(t.stop_ids, t.sched), start=1):
            stop = by_id[sid]
            booking = 2 if stop.optional else 0    # 2 = must be arranged in advance
            hms = min_to_hhmmss(time)
            stop_times.append({"trip_id": t.trip_id, "arrival_time": hms, "departure_time": hms,
                               "stop_id": sid, "stop_sequence": seq, "pickup_type": booking,
                               "drop_off_type": booking, "timepoint": int(stop.timing_point)})

    tables = {
        "agency.txt": [{"agency_id": "A1", "agency_name": r["agency_name"],
                        "agency_url": r["agency_url"], "agency_timezone": r["timezone"]}],
        "stops.txt": [{"stop_id": s.id, "stop_name": s.name, "stop_lat": s.lat, "stop_lon": s.lon}
                      for s in cfg.stops],
        "routes.txt": [{"route_id": r["id"], "agency_id": "A1", "route_short_name": r["short_name"],
                        "route_long_name": r["long_name"], "route_type": 3}],
        "calendar.txt": [{"service_id": service_id, **dict(zip(WEEK, days)),
                          "start_date": service_start, "end_date": service_end}],
        "trips.txt": [{"route_id": r["id"], "service_id": service_id, "trip_id": t.trip_id,
                       "direction_id": 0 if t.direction == "outbound" else 1} for t in trips],
        "stop_times.txt": stop_times,
    }
    path = out / "gtfs.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, rows in tables.items():
            z.writestr(name, pd.DataFrame(rows).to_csv(index=False))
    return path
