# Stochastic timetable simulator for demand-responsive intercity coaches

Tests a proposed timetable against variable traffic and stop demand before it
runs, then checks whether it is operable: vehicles, battery charge and
drivers' breaks.

Independent portfolio project. Not affiliated with any operator; no operator data used.

## The problem
Clock-face timetables apply one running time all day. On a route where some
stops are only served when booked, journey time depends on traffic *and* on
which stops are triggered. Average running times are too tight in the peak
and wasteful off-peak.

## What it does
1. Stores stops, segments and running-time observations in DuckDB; fits
   lognormal running-time distributions per segment, time band and day type in SQL.
2. Monte Carlo simulation of journeys: time-varying traffic, correlated
   across segments; optional stops served with a probability; dwell and detour time.
3. Builds two timetables: clock-face (daily average) vs time-varying (Pxx per departure).
4. Evaluates punctuality at timing points (1 min early to 5 min 59 s late),
   with coaches held at timing points rather than running early.
5. Operability: vehicle blocks, peak vehicle requirement, winter-case battery
   state of charge with layover charging, and 4.5-hour driving flags.
6. Exports the recommended timetable as GTFS.

## Results
WIP

## Validation


## Data: real vs assumed
| Input | Source | Real or assumed |
|---|---|---|
| Stop locations | NaPTAN | [ ] |
| Running times | [ridden journeys / Routes API / synthetic] | [ ] |
| Optional-stop probabilities | [proxy used] | Assumed |
| Battery and consumption | [published spec / assumption] | [ ] |

## Limitations
- No booking data: stop-demand probabilities are assumptions.
- Knock-on delays between trips not simulated; blocks use scheduled times.
- Constant charging rate; no taper curve or charger contention.
- Simplified drivers' hours (single 45-min break only).

## How I used AI
- AI built up the initial draft of the project, to get it off the ground. I used this as a learning opportunity to sift through the code and learn what was done and why. From here, I plan to iterate on the system, use my background in data analytics to see where the simulation is lacking and improving it.

## Running it
pip install -r requirements.txt
pytest
python -m ttsim.cli run
