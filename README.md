# SELENE — LunaGrid + HEATBANK

SELENE is my personal project exploring how a lunar habitat could manage electrical power and reuse equipment waste heat.
Python simulation + local HTTP API + interactive dashboard. No third-party packages, external fonts, chart CDNs, hardware or internet required.

## Start on Windows

1. Install Python 3.10 or newer if it is not already installed.
2. Clone or download this repository, then open the `selene` folder.
3. Double-click `START_WINDOWS.bat`.
4. Your browser opens at http://127.0.0.1:8765. Keep the terminal window open.
5. Press **Run mission**, or **Step +1 min**. Use **Run full comparison** for all three complete runs.

If the launcher cannot find Python, ensure Python is installed and available through `py` or `python`. You can also open a terminal in this folder and run `python main.py`.
If port 8765 is already occupied: `python main.py --port 8766`.
Stop the program with Ctrl+C in its terminal.

macOS / Linux: `python3 main.py` (or `sh start.sh`).

## Explore the simulation

1. Start Full SELENE. Explain the separate power scheduler and thermal router.
2. Watch science heat flow to the habitat, battery and storage.
3. Inject **Enter eclipse**, then run or step. Solar power drops to zero for 90 minutes; flexible work is deferred.
4. Inject **Thermal route failure**. The direct computer-to-battery route becomes unavailable. Heat can still go to the habitat/storage; stored heat and the electric heater cover battery heating.
5. Run the full comparison. All modes are simulated from the same initial state for 720 minutes, with exactly the same scenario events, including injected faults.
6. Reset to restore the original benchmark.

A live run takes approximately 90 seconds at 8 simulated minutes per real second. Pausing freezes mission time. A fault is queued at the current mission minute and applied on the next step. Repeated solar/route faults are idempotent; another eclipse restarts its 90-minute duration.
Changing controller resets time while retaining the event timeline. Reset clears manual injections and restores the default scenario. The comparison does not modify the live simulation.

## Included features

- Six electrical loads, with priority and flexible task completion.
- Separate baseline, forecast-aware LunaGrid and coordinated Full SELENE modes.
- Computer/science waste heat, battery and habitat temperatures, thermal storage and radiator rejection.
- Configurable deterministic faults: 35% solar degradation at minute 180, 90-minute eclipse at minute 240, and thermal path failure at minute 420.
- State, power flow, delivered heat routes, structured controller reasons and four time-series charts.
- Calculated KPI comparison. Trade-offs remain visible; improvements are not hard-coded.
- Python standard-library server and automatic browser launch.

## Model and limits

All assumptions are in `assumptions.json`. This is a deliberately simplified educational simulation, not a validated lunar habitat model.

Time step: one minute. Electrical battery starts at 80% of 10 kWh. Thermal storage starts precharged at 1 kWh of 5 kWh; this initial energy is explicit. Solar output is 8 kW before damage. Battery charge/discharge efficiency is 95%; useful heat-transfer efficiency is 85%. Storage has a 1%/hour standing loss. Heater efficiency is 100% at the modeled boundary. Battery conversion losses and unmodeled equipment heat leave the controlled thermal boundary.

Electrical ledger: solar = delivered loads + battery stored-energy change + conversion losses + curtailed energy.
Thermal ledger: recoverable equipment heat + electric heating = node energy change + storage energy change + environmental loss + transfer loss + standing loss + radiator rejection.

Habitat/battery use lumped heat capacities and fixed environmental heat-loss rates (40% higher in eclipse). Computer is a heat-source node; radiator is a rejection sink, not separately temperature-solved. No radiation law, fluid network, real lunar day, battery degradation or NASA telemetry. The 12-hour timeline is a compressed demonstration.

LunaGrid is a deterministic priority/deadline-aware heuristic, not MILP, machine learning or a proven optimal scheduler. A 60-minute forecast defers flexible work before shortages; low SOC also defers it. Approaching deadlines lower its flexible-work reserve threshold. Critical loads are dispatched first. Reserve is a scheduling target, not a guaranteed floor during deficits. Critical load supply can fail under sufficiently severe injected events.

HEATBANK routes waste heat to immediate needs, then surplus into storage, otherwise the radiator. Storage discharges to remaining needs. The coordinator reduces requested electric heating by delivered useful heat. When heat-producing equipment is power-shed, the step conservatively cancels recovery/storage dispatch and rejects actual source heat; it never creates heat from unpowered loads. It does not re-optimize the heater during that fallback step.

Recovered heat counts useful heat at initial recovery (including storage charging), not again when storage is discharged. Heater energy avoided is a modeled per-step thermal-demand estimate, not a separate replay of baseline. The main comparison uses actual heater electricity from independent controller runs. Thermal violation minutes count each minute in which either node is outside its safe range. Initial storage can contribute to heating savings.

Baseline runs released tasks while power and its fixed 20% flexible-load threshold permit. It has the same physical limits and initial state, rejects waste heat, and uses electric heating. Tasks can be paused/resumed but earn progress only when fully supplied; unfinished tasks stop at their deadlines. Life support and communications define critical-load availability.

## Reproduce the results

From the `selene` folder:

```
python -m unittest discover -s tests -v
python simulation.py
```

`benchmark_results.json` contains results generated by the current default scenario. Tests cover repeated resets/runs, energy residuals below 1e-7 Wh, electrical and thermal storage bounds, severe all-mission eclipse, fault routing, forecast postponement and resumption, and comparison outcomes.

The Python test suite passes with `python -m unittest discover -s tests -v`. The dashboard and launchers should also be checked on the target machine.

## API

GET `/state`, `/history`, `/metrics`, `/decisions`.
POST `/reset`, `/start`, `/pause`, `/step`, `/compare` accept `{}`.
POST `/mode`: `{"mode":"baseline"}` / `lunagrid` / `full`.
POST `/fault`: `{"fault":"solar_damage"}` / `eclipse` / `thermal_route_failure`.

The server binds only to localhost, keeps one in-memory mission shared by tabs, and loses that state when closed. No accounts or persistent database.

## Files

- `main.py`: local server, API and simulation clock.
- `simulation.py`: physical balances, controller policies, events and metrics.
- `assumptions.json`: all configurable physical/scenario assumptions.
- `static/index.html`: self-contained dashboard and SVG charts.
- `tests/test_simulation.py`: deterministic and conservation checks.
- `benchmark_results.json`: generated default benchmark results.
- `START_WINDOWS.bat`, `start.sh`: launchers.

I kept the simulation in a single module for readability. Controller branches are explicit and can later be split into separate modules or replaced with an optimization solver.
