"""Collect traffic-aware driving-time estimates from the Google Maps Routes API.

- Costs money beyond the free allowance: check current pricing first.
- Check the request format against Google's current documentation.
- Estimates are for cars: converted to coach time with a factor and the coach speed cap.
- A forecast is not a distribution: BEST_GUESS alone understates variability.
  Use PESSIMISTIC as a stress test and ridden journeys for real spread.
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, ".")
from ttsim.config import DIRECTIONS, hhmm_to_min, load_config  # noqa: E402

URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def car_minutes(key, a, b, when, model):
    body = {
        "origin": {"location": {"latLng": {"latitude": a.lat, "longitude": a.lon}}},
        "destination": {"location": {"latLng": {"latitude": b.lat, "longitude": b.lon}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "trafficModel": model,
        "departureTime": when.isoformat(),
    }
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"}
    r = requests.post(URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return float(r.json()["routes"][0]["duration"].rstrip("s")) / 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/corridor_example.toml")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--first", default="06:00")
    ap.add_argument("--last", default="21:00")
    ap.add_argument("--step-min", type=int, default=60)
    ap.add_argument("--models", nargs="*", default=["BEST_GUESS", "PESSIMISTIC"])
    ap.add_argument("--coach-factor", type=float, default=1.10)
    ap.add_argument("--out", default="data/routes_api.csv")
    ap.add_argument("--yes", action="store_true", help="confirm you accept the request count")
    args = ap.parse_args()

    cfg = load_config(args.config)
    stops = {s.id: s for s in cfg.stops}
    tz = ZoneInfo(cfg["route"]["timezone"])
    cap = cfg["operations"]["coach_speed_cap_kmh"]
    minutes = list(range(hhmm_to_min(args.first), hhmm_to_min(args.last) + 1, args.step_min))
    n_req = args.days * len(minutes) * 2 * len(cfg.segments) * len(args.models)
    print(f"This will make {n_req} API requests.")
    if not args.yes:
        raise SystemExit("Re-run with --yes to proceed.")

    key = os.environ["GOOGLE_MAPS_API_KEY"]
    start = (datetime.now(tz) + timedelta(days=1)).date()    # departure times must be in the future
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["segment_id", "obs_date", "depart_min", "day_type", "run_min", "source"])
        for d in range(args.days):
            day = start + timedelta(days=d)
            day_type = "weekend" if day.weekday() >= 5 else "weekday"
            for minute in minutes:
                when = datetime(day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=tz)
                for direction in DIRECTIONS:
                    for seg in cfg.segments_for(direction):
                        for model in args.models:
                            car = car_minutes(key, stops[seg.from_id], stops[seg.to_id], when, model)
                            coach = max(car * args.coach_factor, seg.distance_km / cap * 60)
                            w.writerow([seg.id, day.isoformat(), minute, day_type,
                                        round(coach, 2), f"routes_api_{model.lower()}"])
                            time.sleep(0.1)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
