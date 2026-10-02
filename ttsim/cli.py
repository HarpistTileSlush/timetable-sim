"""Entry point.
python -m ttsim.cli run --config config/corridor_example.toml
python -m ttsim.cli validate --journeys data/my_journeys.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import db, plots, synthetic
from .config import DIRECTIONS, load_config
from .gtfs import export_gtfs
from .operability import build_blocks
from .simulate import SimSettings, build_route_model
from .timetable import build_timetable, evaluate, summarise, to_frame
from .validate import calibration, journeys_to_observations


def _settings(cfg):
    sim = cfg["simulation"]
    return SimSettings(int(sim["n_runs"]), float(sim["segment_correlation"]),
                       np.random.default_rng(sim["seed"]))


def _load(cfg, rng, sources, observations, journeys, db_path=":memory:"):
    con = db.connect(db_path)
    db.load_bands(con, cfg)
    if "synthetic" in sources:
        db.add_observations(con, synthetic.generate(cfg, rng))
    for path in observations:
        db.add_observations(con, pd.read_csv(path))
    for path in journeys:
        db.add_observations(con, journeys_to_observations(pd.read_csv(path, dtype=str), cfg))
    return db.fit_params(con, cfg, sources)


def cmd_run(args):
    cfg = load_config(args.config)
    s = _settings(cfg)
    sources = args.sources.split(",")
    params = _load(cfg, s.rng, sources, args.observations, args.journeys, args.db)
    day_type = cfg["timetable"]["day_type"]
    models = {d: build_route_model(cfg, params, d, day_type) for d in DIRECTIONS}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    q = cfg["punctuality"]["target_percentile"]

    results = {}
    for label, kind, pct in [("clock_face", "flat", None), (f"p{round(q * 100)}", "percentile", q)]:
        trips = build_timetable(cfg, models, s, kind, pct)
        ev = evaluate(trips, models, cfg, s)
        ops = build_blocks(trips, cfg)
        summary = summarise(ev, trips) | {"peak_vehicles": ops["peak_vehicles"],
                                          "driver_break_flags": len(ops["driver_flags"])}
        results[label] = (trips, ev, summary)
        to_frame(trips).to_csv(out / f"{label}_timetable.csv", index=False)
        ev.to_csv(out / f"{label}_punctuality.csv", index=False)
        ops["blocks"].to_csv(out / f"{label}_blocks.csv", index=False)
        ops["driver_flags"].to_csv(out / f"{label}_driver_flags.csv", index=False)

    rows = []
    for pct in args.sweep:
        trips = build_timetable(cfg, models, s, "percentile", pct)
        ev = evaluate(trips, models, cfg, s)
        rows.append({"percentile": pct, **summarise(ev, trips),
                     "peak_vehicles": build_blocks(trips, cfg)["peak_vehicles"]})
    sens = pd.DataFrame(rows)
    sens.to_csv(out / "sensitivity.csv", index=False)

    (tf, evf, _), (tp, evp, _) = results["clock_face"], results[f"p{round(q * 100)}"]
    plots.punctuality_by_departure(evf, evp, q, out / "punctuality_by_departure.png")
    plots.scheduled_time_by_departure(tf, tp, out / "scheduled_time_by_departure.png")
    plots.tradeoff(sens, out / "tradeoff.png")
    export_gtfs(tp, cfg, out)

    summaries = {k: v[2] for k, v in results.items()}
    (out / "summary.json").write_text(json.dumps(summaries, indent=2, default=float))
    print(pd.DataFrame(summaries).round(3).to_string())
    print(f"\nOutputs written to {out.resolve()}")


def cmd_validate(args):
    cfg = load_config(args.config)
    sources = args.sources.split(",")
    if "observed" in sources:
        raise SystemExit("Fit on sources other than 'observed' so the check is out-of-sample.")
    s = _settings(cfg)
    params = _load(cfg, s.rng, sources, args.observations, [])
    obs = journeys_to_observations(pd.read_csv(args.journeys, dtype=str), cfg)
    report = calibration(obs, params, cfg)
    if report.empty:
        raise SystemExit("No observed legs matched modelled segments.")
    report.to_csv(args.out, index=False)
    p = report.percentile_in_model
    print(report.round(3).to_string(index=False))
    print(f"\nMean percentile {p.mean():.2f} (0.50 if unbiased); "
          f"{(p > 0.9).mean():.0%} above P90 and {(p < 0.1).mean():.0%} below P10 "
          "(about 10% each if the spread is right).")


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config/corridor_example.toml")
    common.add_argument("--sources", default="synthetic",
                        help="comma-separated sources to fit on, e.g. synthetic,observed,routes_api_best_guess")
    common.add_argument("--observations", nargs="*", default=[], help="CSV files in observations format")

    ap = argparse.ArgumentParser(prog="ttsim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", parents=[common])
    r.add_argument("--journeys", nargs="*", default=[], help="ridden-journey CSVs (source 'observed')")
    r.add_argument("--out", default="outputs")
    r.add_argument("--db", default=":memory:")
    r.add_argument("--sweep", nargs="*", type=float, default=[0.5, 0.7, 0.85, 0.95])
    v = sub.add_parser("validate", parents=[common])
    v.add_argument("--journeys", required=True)
    v.add_argument("--out", default="outputs/calibration.csv")

    args = ap.parse_args(argv)
    {"run": cmd_run, "validate": cmd_validate}[args.cmd](args)


if __name__ == "__main__":
    main()
