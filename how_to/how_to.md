# Notebooks — Sample Data Guide

```
how_to/
├── guides/          # Full reference notebooks (detailed explanations)
│   ├── 01_labelling_guide.ipynb
│   ├── 02_risk_score_guide.ipynb
│   └── 03_continuous_scoring.ipynb
├── examples/        # Lean executable notebooks + sample data
│   ├── 01a_labelling_fixed_log.ipynb
│   ├── 01b_labelling_free_text.ipynb
│   ├── 02a_risk_score_fixed_log_supervised.ipynb
│   ├── 02b_risk_score_fixed_log_unsupervised.ipynb
│   ├── 02c_risk_score_free_text_unsupervised.ipynb
│   ├── 02d_risk_score_free_text_supervised.ipynb
│   └── sample_data/
│       ├── fixed_log_training.csv
│       ├── fixed_log_generation.csv
│       ├── fixed_log_failures.csv
│       ├── free_text_training.csv
│       ├── free_text_generation.csv
│       └── free_text_failures.csv
└── README.md
```

**Start here:** Read the relevant guide notebook in `guides/` first, then run the matching example notebook in `examples/` against the sample data.

---

## Dataset 1 — Airport Baggage Management System (fixed-log)

**Used by:** `examples/01a_labelling_fixed_log.ipynb`, `examples/02a_risk_score_fixed_log_supervised.ipynb`, `examples/02b_risk_score_fixed_log_unsupervised.ipynb`

This dataset represents fault event logs from 12 Airport baggage management stations at a busy international airport. Each row is a single fault event recorded against a station on a given date.

| Property | Value |
|---|---|
| Assets | `ASS-001` to `ASS-012` (12 sortation stations) |
| Log column | `event_code` — short structured fault descriptions |
| Timestamp column | `date` (format `DD/MM/YYYY`) |
| Training period | Jan–Dec 2023 (~12,000 rows) |
| Generation period | Jan–Mar 2024 (~2,700 rows) |
| Unique event codes | 31, spanning 5 system domains |

The 31 event codes cover five operational domains that the labelling step will discover automatically:

| Domain | Example event codes |
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

**Used by:** `examples/01b_labelling_free_text.ipynb`, `examples/02c_risk_score_free_text_unsupervised.ipynb`, `examples/02d_risk_score_free_text_supervised.ipynb`

This dataset represents natural-language maintenance notes logged by technicians servicing HVAC units fitted to passenger rolling stock. Each row is a single maintenance note recorded at depot or during a service visit.

| Property | Value |
|---|---|
| Assets | `HVAC-01` to `HVAC-08` (8 HVAC units across the fleet) |
| Log column | `maintenance_log` — free-text technician notes |
| Timestamp column | `date` (format `DD/MM/YYYY`) |
| Training period | Jan–Dec 2023 (~5,000 rows) |
| Generation period | Jan–Mar 2024 (~1,100 rows) |

The notes cover five system domains:

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

## File summary

| File | Rows | Period | Used for |
|---|---|---|---|
| `sample_data/fixed_log_training.csv` | ~12,000 | Jan–Dec 2023 | Labelling + risk score training |
| `sample_data/fixed_log_generation.csv` | ~2,700 | Jan–Mar 2024 | Risk score generation |
| `sample_data/fixed_log_failures.csv` | 28 | 2023 + Feb–Mar 2024 | Supervised training + failure performance plots |
| `sample_data/free_text_training.csv` | ~5,000 | Jan–Dec 2023 | Labelling + risk score training |
| `sample_data/free_text_generation.csv` | ~1,100 | Jan–Mar 2024 | Risk score generation |
| `sample_data/free_text_failures.csv` | 20 | 2023 + Feb–Mar 2024 | Supervised training + failure performance plots |
