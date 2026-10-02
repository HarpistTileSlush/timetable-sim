"""Charts for the README."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def punctuality_by_departure(ev_flat, ev_pct, target, path):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for ev, label in [(ev_flat, "Clock-face (average running time)"),
                      (ev_pct, f"Time-varying (P{round(target * 100)})")]:
        fin = ev[ev.final_stop & (ev.direction == "outbound")].sort_values("dep_min")
        ax.plot(fin.dep_min / 60, fin.on_time * 100, marker="o", label=label)
    ax.axhline(target * 100, ls="--", c="grey", lw=1)
    ax.set(xlabel="Departure hour", ylabel="On time at final stop (%)",
           title="Simulated punctuality by departure (outbound)", ylim=(0, 102))
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def scheduled_time_by_departure(trips_flat, trips_pct, path):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for trips, label in [(trips_flat, "Clock-face"), (trips_pct, "Time-varying")]:
        out = [t for t in trips if t.direction == "outbound"]
        ax.plot([t.dep_min / 60 for t in out], [t.arr_min - t.dep_min for t in out],
                marker="o", label=label)
    ax.set(xlabel="Departure hour", ylabel="Scheduled end-to-end (min)",
           title="Scheduled journey time by departure (outbound)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def tradeoff(sens, path):
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(sens.percentile * 100, sens.on_time_final_stop * 100, marker="o", c="tab:blue")
    ax1.set(xlabel="Timetable percentile", ylabel="On time at final stop (%)")
    ax2 = ax1.twinx()
    ax2.step(sens.percentile * 100, sens.peak_vehicles, where="mid", c="tab:orange")
    ax2.set_ylabel("Vehicles required", color="tab:orange")
    ax1.set_title("Reliability vs fleet: the planning trade-off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
