# Notebooks — Sample Data Guide

```
how_to/
├── guides/          # Full reference notebooks (detailed explanations)
│   ├── 01_labelling_guide.ipynb
│   ├── 02_risk_score_guide.ipynb
│   └── 03_fleet_app_guide.ipynb
├── examples/        # Lean executable notebooks + sample data
│   ├── 01a_labelling_fixed_log.ipynb
│   ├── 01b_labelling_free_text.ipynb
│   ├── 02a_risk_score_fixed_log_supervised.ipynb
│   ├── 02b_risk_score_fixed_log_unsupervised.ipynb
│   ├── 02c_risk_score_free_text_unsupervised.ipynb
│   ├── 02d_risk_score_free_text_supervised.ipynb
│   ├── 03a_fleet_app_fixed_log.ipynb
│   ├── 03b_fleet_app_free_text.ipynb
│   └── sample_data/             # one folder per example fleet
│       ├── airport_baggage_conveyors/   # fixed-log: 12 baggage sortation stations
│       │   ├── README.md                # the data, its files and which notebooks use it
│       │   ├── training.csv
│       │   ├── generation.csv
│       │   ├── failures.csv
│       │   ├── batches/                 # generation.csv split into weekly files, week_01.csv … week_13.csv
│       │   └── models/                  # ready-made models, so you can start at any stage
│       │       ├── labelling_model.zip
│       │       └── complete_model.zip
│       └── rolling_stock_hvac/          # free-text: 8 train air-conditioning units
│           └── (the same files)
└── how_to.md
```

**Getting these files:** `amygda-risk-skill examples` downloads this folder, as `amygda_how_to/`, into the folder you run it from. Run the example notebooks from inside `examples/`, since they find the sample data relative to it.

**Start here:** Read the relevant guide notebook in `guides/` first, then run the matching example notebook in `examples/` against the sample data.

**Start at any stage.** Each stage needs the model the previous one made. If you haven't run it, the notebooks use the ready-made models in each example's `models/` folder instead (see "Ready-made models" below), so you can go straight to risk scoring, or to the fleet app.

---

## The examples

Each folder in `sample_data/` is one example fleet with everything for it: the history to train on, new data to score, failure records, the new data in weekly batches for the fleet app, and ready-made models. Its `README.md` describes the data.

| Example | Log type | Assets | Log column | Used by |
|---|---|---|---|---|
| [`airport_baggage_conveyors/`](examples/sample_data/airport_baggage_conveyors/README.md) | Fixed-log: short fault codes | `ASS-001` to `ASS-012`, 12 baggage sortation stations at an airport | `event_code` | `01a`, `02a`, `02b`, `03a`, `guides/01`, `guides/02` |
| [`rolling_stock_hvac/`](examples/sample_data/rolling_stock_hvac/README.md) | Free-text: technicians' notes | `HVAC-01` to `HVAC-08`, 8 air-conditioning units on passenger trains | `maintenance_log` | `01b`, `02c`, `02d`, `03b` |

Both use `asset_id` for the asset and `date` (date and time, `YYYY-MM-DD HH:MM:SS`) for the time. The failures files have `asset_id` and `failure_date`. Training covers Jan–Dec 2023 and new data Jan–Mar 2024.

---

## Weekly batches (the fleet app)

**Used by:** `examples/03a_fleet_app_fixed_log.ipynb`, `examples/03b_fleet_app_free_text.ipynb`

Each example's `batches/` folder holds its `generation.csv` split into 13 weekly files, `week_01.csv` to `week_13.csv`, in the same columns. They stand in for the files a site would export each week, so you can add them to the fleet app one at a time.

| | `airport_baggage_conveyors` | `rolling_stock_hvac` |
|---|---|---|
| Rows per week | ~220–470 | ~55–137 |
| Assets in every week | all 12 | all 8 |

- Weeks start on Mondays (1 Jan 2024 is a Monday).
- Week 6 ends at noon on Wednesday 14 February and week 7 starts there, so one batch ends part-way through a day. For a daily or 12-hourly model, that period is provisional until week 7 arrives.
- Joined together, the 13 files are exactly the generation file.
- The training file ends the day before week 1 starts, so it can be given to the monitor as history (`amygda-risk init --history`).

---

## Ready-made models

Trained on the sample data, so each stage can be tried without running the ones before it. The notebooks use your own model when you've made one, and these otherwise. Each example's `models/` folder has:

| File | What it is | Used by (when you haven't made your own) |
|---|---|---|
| `labelling_model.zip` | Labelling model (Steps 1–8) | `02a`, `02b`, `guides/02_risk_score_guide.ipynb` (airport baggage); `02c`, `02d` (HVAC) |
| `complete_model.zip` | Complete model (Steps 1–12), unsupervised, as `02b` / `02c` make it: 7-day `sum` window, scored every 2 hours (airport baggage) or 12 hours (HVAC) | `03a` (airport baggage), `03b` (HVAC) |

The labelling step uses an LLM, so a hierarchy you build yourself will have different system and subsystem names from these.
