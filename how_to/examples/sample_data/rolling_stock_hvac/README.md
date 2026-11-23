# Rolling stock HVAC (free-text)

Maintenance notes written by technicians servicing the air-conditioning (HVAC) units on a fleet of passenger trains. Each row is one note, recorded at the depot or during a service visit. The data is made up for these examples.

## Files

| File | Rows | Period | What it is |
|---|---|---|---|
| `training.csv` | ~6,000 | Jan–Dec 2023 | History: labelling and risk score training |
| `generation.csv` | ~1,300 | Jan–Mar 2024 | New data to score |
| `failures.csv` | 20 | 2023 + Feb–Mar 2024 | Failure records: supervised training and the failure plots |
| `batches/week_01.csv` … `week_13.csv` | ~55–137 a week | Jan–Mar 2024 | `generation.csv` split into weeks, to add to the fleet app one at a time |
| `models/labelling_model.zip` | | | Ready-made labelling model (Steps 1–8) |
| `models/complete_model.zip` | | | Ready-made complete model (Steps 1–12), unsupervised: 7-day `sum` window, scored every 12 hours |

## The data

| Property | Value |
|---|---|
| Assets | `HVAC-01` to `HVAC-08` (8 HVAC units across the fleet) |
| Asset column | `asset_id` |
| Log column | `maintenance_log`: free-text technician notes |
| Timestamp column | `date`: date and time, `YYYY-MM-DD HH:MM:SS` |

The labelling step finds the systems for itself. It uses an LLM, so the names and number of systems vary from run to run and with the numbers you choose, and a model you build will differ from the ready-made one. The notes cover these areas:

| Area | Example notes |
|---|---|
| Refrigeration | "Compressor suction pressure lower than expected, possible refrigerant leak" |
| Electrical | "Capacitor showing signs of aging, voltage readings below spec" |
| Airflow | "Supply fan belt worn, replacement required" |
| Controls & automation | "BMS communication timeout on unit, manual override applied" |
| Safety & compliance | "High-pressure safety cutout triggered" |

**Signal design:** units `HVAC-03` and `HVAC-07` are high-fault assets with a higher baseline log rate. Their log rate doubles in the 14 days before each recorded failure.

**Failures:** `failures.csv` has 20 failures across 5 units (HVAC-01, 02, 03, 04 and 07): 17 in the training period (2023) and 3 in the new data (Feb–Mar 2024).

## Used by

- `examples/01b_labelling_free_text.ipynb`: labelling
- `examples/02c_risk_score_free_text_unsupervised.ipynb`, `examples/02d_risk_score_free_text_supervised.ipynb`: risk scores, from `models/labelling_model.zip` if you haven't labelled
- `examples/03b_fleet_app_free_text.ipynb`: the fleet app, from `models/complete_model.zip` if you haven't scored

`how_to.md` at the top of the how-to folder explains how the weekly batches are cut.
