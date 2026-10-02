"""Load and validate the corridor configuration."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DIRECTIONS = ("outbound", "inbound")


def hhmm_to_min(s: str) -> int:
    h, m = s.strip().split(":")[:2]
    return int(h) * 60 + int(m)


def min_to_hhmmss(x: float) -> str:
    total = int(round(x * 60))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"   # GTFS allows hours >= 24


@dataclass
class Stop:
    id: str
    name: str
    lat: float = 0.0
    lon: float = 0.0
    optional: bool = False
    timing_point: bool = True
    charger: bool = False
    serve_prob: dict = field(default_factory=dict)
    detour_s: float = 0.0
    dwell_median_s: float = 0.0
    dwell_sigma: float = 0.3


@dataclass
class Segment:
    from_id: str
    to_id: str
    distance_km: float
    freeflow_min: float
    congestion_sensitivity: float = 1.0

    @property
    def id(self) -> str:
        return f"{self.from_id}>{self.to_id}"

    def reversed(self) -> "Segment":
        return Segment(self.to_id, self.from_id, self.distance_km,
                       self.freeflow_min, self.congestion_sensitivity)


@dataclass
class Config:
    raw: dict
    stops: list[Stop]
    segments: list[Segment]          # outbound order
    bands: list[tuple[str, int, int]]

    def __getitem__(self, key):
        return self.raw[key]

    def stops_for(self, direction: str) -> list[Stop]:
        return self.stops if direction == "outbound" else self.stops[::-1]

    def segments_for(self, direction: str) -> list[Segment]:
        if direction == "outbound":
            return self.segments
        return [s.reversed() for s in self.segments[::-1]]


def load_config(path) -> Config:
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    stops = [Stop(**s) for s in raw["stops"]]
    segments = [
        Segment(from_id=s["from"], to_id=s["to"], distance_km=s["distance_km"],
                freeflow_min=s["freeflow_min"],
                congestion_sensitivity=s.get("congestion_sensitivity", 1.0))
        for s in raw["segments"]
    ]
    bands = sorted(((name, int(a), int(b)) for name, (a, b) in raw["bands"].items()),
                   key=lambda x: x[1])
    _validate(stops, segments, bands)
    return Config(raw, stops, segments, bands)


def _validate(stops, segments, bands):
    ids = [s.id for s in stops]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate stop ids")
    if len(segments) != len(stops) - 1:
        raise ValueError("Need exactly one segment between each pair of consecutive stops")
    for i, seg in enumerate(segments):
        if (seg.from_id, seg.to_id) != (ids[i], ids[i + 1]):
            raise ValueError(f"Segment {i} should run {ids[i]} -> {ids[i + 1]}")
    for s in (stops[0], stops[-1]):
        if s.optional or not s.timing_point:
            raise ValueError(f"Terminus {s.id} must be a mandatory timing point")
    for s in stops:
        if s.optional and s.timing_point:
            raise ValueError(f"{s.id}: optional stops cannot be timing points")
        if s.optional and not s.serve_prob:
            raise ValueError(f"{s.id}: optional stops need serve_prob")
    if bands[0][1] != 0 or bands[-1][2] != 1440:
        raise ValueError("Bands must cover 0-1440 minutes")
    for (_, _, end), (_, start, _) in zip(bands, bands[1:]):
        if end != start:
            raise ValueError("Bands must be contiguous")
