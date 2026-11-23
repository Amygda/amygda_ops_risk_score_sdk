# Aircraft fault messages (fixed-log)

Fault messages reported by the onboard maintenance systems of an airline's 20 narrow-body aircraft. Each row is one message, recorded against an aircraft at a given time. The airline's reliability engineers want to know which aircraft are heading for an unscheduled component removal, such as a bleed valve, a hydraulic pump or a brake unit. The data is made up for these examples.

## Files

| File | Rows | Period | What it is |
|---|---|---|---|
| `training.csv` | ~21,700 | Jan–Dec 2023 | History: labelling and risk score training |
| `generation.csv` | ~5,300 | Jan–Mar 2024 | New data to score |
| `failures.csv` | 30 | 2023 + Feb–Mar 2024 | Unscheduled component removals: supervised training and the failure plots |
| `batches/week_01.csv` … `week_13.csv` | ~240–530 a week | Jan–Mar 2024 | `generation.csv` split into weeks, to add to the fleet app one at a time |
| `models/labelling_model.zip` | | | Ready-made labelling model (Steps 1–8) |
| `models/complete_model.zip` | | | Ready-made complete model (Steps 1–12), unsupervised: 7-day `sum` window, scored every 8 hours |

## The data

| Property | Value |
|---|---|
| Assets | `AC-101` to `AC-120` (20 aircraft) |
| Asset column | `asset_id` |
| Log column | `event_code`: short standard fault messages |
| Timestamp column | `date`: date and time, `YYYY-MM-DD HH:MM:SS` |
| Unique messages | 39, across 9 areas |

The labelling step finds the systems for itself. It uses an LLM, so the names and number of systems vary from run to run and with the numbers you choose, and a model you build will differ from the ready-made one. The messages cover these areas:

| Area | Example messages |
|---|---|
| Air conditioning | PACK 1 FAULT, PACK OUTLET OVERHEAT, CABIN TEMP CONTROLLER FAULT |
| Bleed air | BLEED 1 PRESSURE HIGH, BLEED DUCT LEAK, BLEED COOLER OUTLET TEMP HIGH |
| Hydraulics | HYDRAULIC GREEN SYSTEM LOW PRESSURE, HYDRAULIC RESERVOIR LOW LEVEL |
| Landing gear and brakes | BRAKE OVERHEAT, BRAKE WEAR LIMIT INDICATION, ANTI-SKID FAULT, TIRE PRESSURE LOW |
| Fuel | FUEL PUMP LOW PRESSURE, FUEL FILTER CLOG, FUEL IMBALANCE |
| Electrical | GENERATOR 1 FAILURE, DRIVE GENERATOR OIL TEMP HIGH, TRANSFORMER RECTIFIER FAULT |
| Auxiliary power unit | AUXILIARY POWER UNIT AUTO SHUTDOWN, AUXILIARY POWER UNIT STARTER FAULT |
| Engines | ENGINE 1 VIBRATION HIGH, ENGINE 2 OIL PRESSURE LOW, ENGINE OIL FILTER CLOG |
| Routine | SCHEDULED CHECK COMPLETED, MAINTENANCE TEST PASSED, DATA LOADER UPLOAD COMPLETED |

**Signal design:**
- Aircraft `AC-104`, `AC-111` and `AC-117` report about twice the usual number of messages.
- Before each removal, two or three messages tied to the failing part become more frequent each day over 14–21 days, and the aircraft's overall message rate doubles in the last 14 days. For example, BLEED 1 PRESSURE HIGH, BLEED DUCT LEAK and BLEED COOLER OUTLET TEMP HIGH build up before a bleed valve removal.
- After the removal, the aircraft logs MAINTENANCE TEST PASSED.

**Failures:** `failures.csv` has 30 removals on 11 aircraft. 26 are in the training period (2023) and 4 are in the new data: `AC-120` (2 Feb), `AC-111` (5 Feb and 25 Mar) and `AC-104` (4 Mar 2024). The parts removed are bleed valves, pack valves, hydraulic pumps, brake units, fuel pumps, drive generators, APU starters and engine oil pumps.

With the ready-made model, AC-104 and AC-111 reach the high band within a day of their March removals, and AC-120 reaches the watch band five days before its removal.

## Notebook settings

Use the fixed-log notebooks with these settings. Also change the asset, system and subsystem names in the plot cells to ones from this data.

| Notebook | Settings |
|---|---|
| `01a_labelling_fixed_log.ipynb` | `FILE_PATH = "sample_data/aircraft_fault_messages/training.csv"`, `ASSET_CONTEXT = "commercial narrow-body aircraft"`, `MAX_SYSTEMS = 9` (the ready-made model used these, with `MAX_SUBSYSTEMS = 4`) |
| `02a_risk_score_fixed_log_supervised.ipynb`, `02b_risk_score_fixed_log_unsupervised.ipynb` | `ZIP_PATH`, `TRAINING_FILE`, `GENERATION_FILE` (and the failures file for `02a`) in `sample_data/aircraft_fault_messages/` |
| `03a_fleet_app_fixed_log.ipynb` | `MODEL` and `TRAINING` in `sample_data/aircraft_fault_messages/`, and a deployment name of your own |

`how_to.md` at the top of the how-to folder explains how the weekly batches are cut.
