# Notebooks — Sample Data Guide

```
how_to/
├── guides/          # Full reference notebooks (detailed explanations)
│   ├── 01_labelling_guide.ipynb
│   ├── 02_risk_score_guide.ipynb
│   └── 03_deploy_and_monitor_guide.ipynb
├── examples/        # Lean executable notebooks + sample data
│   ├── 01a_labelling_fixed_log.ipynb
│   ├── 01b_labelling_free_text.ipynb
│   ├── 02a_risk_score_fixed_log_supervised.ipynb
│   ├── 02b_risk_score_fixed_log_unsupervised.ipynb
│   ├── 02c_risk_score_free_text_unsupervised.ipynb
│   ├── 02d_risk_score_free_text_supervised.ipynb
│   ├── 03a_deploy_and_monitor_fixed_log.ipynb
│   ├── 03b_deploy_and_monitor_free_text.ipynb
│   └── sample_data/
│       ├── fixed_log_training.csv
│       ├── fixed_log_generation.csv
│       ├── fixed_log_failures.csv
│       ├── free_text_training.csv
│       ├── free_text_generation.csv
│       ├── free_text_failures.csv
│       ├── batches/                 # the generation data split into weekly files
│       │   ├── fixed_log/week_01.csv … week_13.csv
│       │   └── free_text/week_01.csv … week_13.csv
│       └── models/                  # ready-made models, so you can start at any stage
│           ├── fixed_log_labelling_model.zip
│           ├── free_text_labelling_model.zip
│           ├── fixed_log_complete_model.zip
│           └── free_text_complete_model.zip
└── how_to.md
```

**Start here:** Read the relevant guide notebook in `guides/` first, then run the matching example notebook in `examples/` against the sample data.

**Start at any stage.** Each stage needs the model the previous one made. If you haven't run it, the notebooks use the ready-made models in `sample_data/models/` instead (see "Ready-made models" below), so you can go straight to risk scoring, or to deploy and monitor.

---

## Dataset 1 — Airport Baggage Management System (fixed-log)

**Used by:** `examples/01a_labelling_fixed_log.ipynb`, `examples/02a_risk_score_fixed_log_supervised.ipynb`, `examples/02b_risk_score_fixed_log_unsupervised.ipynb`, `examples/03a_deploy_and_monitor_fixed_log.ipynb`, `guides/03_deploy_and_monitor_guide.ipynb`

This dataset represents fault event logs from 12 Airport baggage management stations at a busy international airport. Each row is a single fault event recorded against a station on a given date.

| Property | Value |
|---|---|
| Assets | `ASS-001` to `ASS-012` (12 sortation stations) |
| Log column | `event_code` — short structured fault descriptions |
| Timestamp column | `date` (format `DD/MM/YYYY`) |
| Training period | Jan–Dec 2023 (~12,000 rows) |
| Generation period | Jan–Mar 2024 (~2,700 rows) |
| Unique event codes | 31, spanning 5 system domains |

The 31 event codes cover operational systems that the labelling step will discover automatically. Some examples are as follows. The actual system names or systems might be different as its probabilistic in nature. The total number of systems will also depend on the numbers you specify :

| System | Example event codes |
|---|---|
| Mechanical drive | Motor overtemperature fault, Belt tracking deviation detected, Gearbox oil level low |
| Sensor network | Photoelectric sensor fault, Barcode reader timeout, RFID tag not detected |
| Control system | PLC communication error, SCADA connection lost, Watchdog timer expired |
| Safety interlock | Emergency stop activated, Light curtain interrupted, Overload protection triggered |
| Maintenance status | Scheduled lubrication due, Filter replacement required, Bearing vibration elevated |

**Signal design:** Stations `ASS-003`, `ASS-007`, and `ASS-011` are high-fault assets with an elevated baseline event rate. Their fault rate doubles in the 14 days before each recorded failure — giving the supervised model a clear signal to learn from.

**Failure files:**
- `fixed_log_failures.csv` — 28 failures; 25 in the training period (2023) and 3 in the generation period (Feb–Mar 2024) on the bad actor assets, so failure performance plots work across both periods.

---

## Dataset 2 — Rolling Stock HVAC Units (free-text)

**Used by:** `examples/01b_labelling_free_text.ipynb`, `examples/02c_risk_score_free_text_unsupervised.ipynb`, `examples/02d_risk_score_free_text_supervised.ipynb`, `examples/03b_deploy_and_monitor_free_text.ipynb`

This dataset represents natural-language maintenance notes logged by technicians servicing HVAC units fitted to passenger rolling stock. Each row is a single maintenance note recorded at depot or during a service visit.

| Property | Value |
|---|---|
| Assets | `HVAC-01` to `HVAC-08` (8 HVAC units across the fleet) |
| Log column | `maintenance_log` — free-text technician notes |
| Timestamp column | `date` (format `DD/MM/YYYY`) |
| Training period | Jan–Dec 2023 (~5,000 rows) |
| Generation period | Jan–Mar 2024 (~1,100 rows) |

The notes cover the following system domains. The actual system names or systems might be different as its probabilistic in nature. The total number of systems will also depend on the numbers you specify:

| Domain | Example notes |
|---|---|
| Refrigeration | "Compressor suction pressure lower than expected, possible refrigerant leak" |
| Electrical | "Capacitor showing signs of aging, voltage readings below spec" |
| Airflow | "Supply fan belt worn, replacement required" |
| Controls & automation | "BMS communication timeout on unit, manual override applied" |
| Safety & compliance | "High-pressure safety cutout triggered" |

**Signal design:** Units `HVAC-03` and `HVAC-07` are high-fault assets with an elevated baseline log rate. Their log rate doubles in the 14 days before each recorded failure.

**Failure files:**
- `free_text_failures.csv` — 20 failures spread across 5 assets (HVAC-01, 02, 03, 04, 07); 17 in the 2023 training period and 3 in the generation period (Feb–Mar 2024).

---

## Weekly batches (deploy and monitor)

**Used by:** `guides/03_deploy_and_monitor_guide.ipynb`, `examples/03a_deploy_and_monitor_fixed_log.ipynb`, `examples/03b_deploy_and_monitor_free_text.ipynb`

`sample_data/batches/` holds each generation file split into 13 weekly files, `week_01.csv` to `week_13.csv`, in the same columns. They stand in for the files a site would export each week, so the monitor can be fed one batch at a time.

| | Fixed-log | Free-text |
|---|---|---|
| Rows per week | ~220–470 | ~55–140 |
| Assets in every week | all 12 | all 8 |

- Weeks start on Mondays (1 Jan 2024 is a Monday).
- Week 6 ends at noon on Wednesday 14 February and week 7 starts there, so one batch ends part-way through a day. For a daily or 12-hourly model, that period is provisional until week 7 arrives.
- Joined together, the 13 files are exactly the generation file.
- The training file ends the day before week 1 starts, so it can be given to the monitor as history (`amygda-risk init --history`).

---

## Ready-made models

Trained on the sample data, so each stage can be tried without running the ones before it. The notebooks use your own model when you've made one, and these otherwise.

| File | What it is | Used by (when you haven't made your own) |
|---|---|---|
| `models/fixed_log_labelling_model.zip` | Labelling model (Steps 1–8) for dataset 1 | `02a`, `02b`, `guides/02_risk_score_guide.ipynb` |
| `models/free_text_labelling_model.zip` | Labelling model (Steps 1–8) for dataset 2 | `02c`, `02d` |
| `models/fixed_log_complete_model.zip` | Complete model (Steps 1–12), unsupervised, as `02b` makes it: 7-day `sum` window, scored every 2 hours | `03a`, `guides/03_deploy_and_monitor_guide.ipynb` |
| `models/free_text_complete_model.zip` | Complete model (Steps 1–12), unsupervised, as `02c` makes it: 7-day `sum` window, scored every 12 hours | `03b` |

The labelling step uses an LLM, so a hierarchy you build yourself will have different system and subsystem names from these.

---

## File summary

| File | Rows | Period | Used for |
|---|---|---|---|
| `sample_data/fixed_log_training.csv` | ~12,000 | Jan–Dec 2023 | Labelling + risk score training |
| `sample_data/fixed_log_generation.csv` | ~2,700 | Jan–Mar 2024 | Risk score generation |
| `sample_data/fixed_log_failures.csv` | 28 | 2023 + Feb–Mar 2024 | Supervised training + failure performance plots |
| `sample_data/free_text_training.csv` | ~5,000 | Jan–Dec 2023 | Labelling + risk score training |
| `sample_data/free_text_generation.csv` | ~1,100 | Jan–Mar 2024 | Risk score generation |
| `sample_data/free_text_failures.csv` | 20 | 2023 + Feb–Mar 2024 | Supervised training + failure performance plots |
| `sample_data/batches/fixed_log/week_*.csv` | 13 files | Jan–Mar 2024 | Deploy and monitor: weekly batches |
| `sample_data/batches/free_text/week_*.csv` | 13 files | Jan–Mar 2024 | Deploy and monitor: weekly batches |
