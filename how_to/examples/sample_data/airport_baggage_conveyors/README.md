# Airport baggage conveyors (fixed-log)

Fault event logs from 12 baggage sortation stations at a busy international airport. Each row is one fault event, recorded against a station on a given date. The data is made up for these examples.

## Files

| File | Rows | Period | What it is |
|---|---|---|---|
| `training.csv` | ~20,700 | Jan–Dec 2023 | History: labelling and risk score training |
| `generation.csv` | ~4,600 | Jan–Mar 2024 | New data to score |
| `failures.csv` | 27 | 2023 + Feb–Mar 2024 | Failure records: supervised training and the failure plots |
| `batches/week_01.csv` … `week_13.csv` | ~220–470 a week | Jan–Mar 2024 | `generation.csv` split into weeks, to add to the fleet app one at a time |
| `models/labelling_model.zip` | | | Ready-made labelling model (Steps 1–8) |
| `models/complete_model.zip` | | | Ready-made complete model (Steps 1–12), unsupervised: 7-day `sum` window, scored every 2 hours |

## The data

| Property | Value |
|---|---|
| Assets | `ASS-001` to `ASS-012` (12 sortation stations) |
| Asset column | `asset_id` |
| Log column | `event_code`: short structured fault descriptions |
| Timestamp column | `date`: date and time, `YYYY-MM-DD HH:MM:SS` |
| Unique event codes | 31, spanning 5 system domains |

The labelling step finds the systems for itself. It uses an LLM, so the names and number of systems vary from run to run and with the numbers you choose, and a model you build will differ from the ready-made one. Systems it typically finds:

| System | Example event codes |
|---|---|
| Mechanical drive | Motor overtemperature fault, Belt tracking deviation detected, Gearbox oil level low |
| Sensor network | Photoelectric sensor fault, Barcode reader timeout, RFID tag not detected |
| Control system | PLC communication error, SCADA connection lost, Watchdog timer expired |
| Safety interlock | Emergency stop activated, Light curtain interrupted, Overload protection triggered |
| Maintenance status | Scheduled lubrication due, Filter replacement required, Bearing vibration elevated |

**Signal design:** stations `ASS-003`, `ASS-007` and `ASS-011` are high-fault assets with a higher baseline event rate. Their fault rate doubles in the 14 days before each recorded failure, which gives the supervised model a clear signal to learn from.

**Failures:** `failures.csv` has 27 failures: 24 in the training period (2023) and 3 in the new data (Feb–Mar 2024) on the high-fault stations, so the failure plots work for both periods.

## Used by

- `examples/01a_labelling_fixed_log.ipynb`: labelling
- `examples/02a_risk_score_fixed_log_supervised.ipynb`, `examples/02b_risk_score_fixed_log_unsupervised.ipynb`: risk scores, from `models/labelling_model.zip` if you haven't labelled
- `examples/03a_fleet_app_fixed_log.ipynb`: the fleet app, from `models/complete_model.zip` if you haven't scored
- `guides/01_labelling_guide.ipynb`, `guides/02_risk_score_guide.ipynb`

`how_to.md` at the top of the how-to folder explains how the weekly batches are cut.
