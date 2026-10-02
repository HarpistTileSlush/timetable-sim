import numpy as np

from ttsim import db, synthetic
from ttsim.config import DIRECTIONS, load_config
from ttsim.operability import build_blocks
from ttsim.simulate import SimSettings, build_route_model, simulate
from ttsim.timetable import build_timetable

CFG = "config/corridor_example.toml"


def _setup():
    cfg = load_config(CFG)
    rng = np.random.default_rng(1)
    con = db.connect()
    db.load_bands(con, cfg)
    db.add_observations(con, synthetic.generate(cfg, rng))
    params = db.fit_params(con, cfg, ["synthetic"])
    models = {d: build_route_model(cfg, params, d, "weekday") for d in DIRECTIONS}
    return cfg, params, models, SimSettings(500, 0.5, rng)


def test_fit_recovers_synthetic_median():
    cfg, params, _, _ = _setup()
    mu, _ = params[("A>B", "weekday")]
    am = [b[0] for b in cfg.bands].index("am_peak")
    expected = 18.0 * 1.35              # freeflow x factor, sensitivity 1.0
    assert abs(np.exp(mu[am]) / expected - 1) < 0.08


def test_no_early_departure_from_timing_points():
    _, _, models, s = _setup()
    m = models["outbound"]
    sched = 480.0 + np.arange(len(m.stop_ids)) * 1000.0     # deliberately generous
    res = simulate(m, 480, 200, s.rng, 0.5, schedule=sched)
    for k in range(1, len(m.stop_ids) - 1):
        if m.timing[k]:
            assert np.nanmin(res.dep[:, k]) >= sched[k]


def test_schedules_monotonic_and_blocks_built():
    cfg, _, models, s = _setup()
    trips = build_timetable(cfg, models, s, "percentile", 0.85)
    assert all(np.all(np.diff(t.sched) >= 0) for t in trips)
    assert build_blocks(trips, cfg)["peak_vehicles"] >= 2
