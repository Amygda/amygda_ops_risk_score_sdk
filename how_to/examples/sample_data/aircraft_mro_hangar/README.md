# Aircraft MRO hangar (free-text)

Maintenance notes for 12 narrow-body aircraft that a maintenance, repair and overhaul (MRO) organisation looks after for an airline. Each row is one note: a pilot's defect report, a maintenance action, a deferred defect, or a finding raised during a check in the hangar. The data is made up for these examples.

The MRO's problem is turnaround. When an aircraft arrives with more wrong than expected, the hangar visit overruns, and slots, parts and staff are tied up. The risk score flags the aircraft likely to need an unscheduled hangar visit, so the shop can plan slots and order parts before the aircraft arrives.

## Files

| File | Rows | Period | What it is |
|---|---|---|---|
| `training.csv` | ~8,200 | Jan–Dec 2023 | History: labelling and risk score training |
| `generation.csv` | ~2,100 | Jan–Mar 2024 | New data to score |
| `failures.csv` | 24 | 2023 + Feb–Mar 2024 | Unscheduled hangar visits: supervised training and the failure plots |
| `batches/week_01.csv` … `week_13.csv` | ~100–250 a week | Jan–Mar 2024 | `generation.csv` split into weeks, to add to the fleet app one at a time |
| `models/labelling_model.zip` | | | Ready-made labelling model (Steps 1–8) |
| `models/complete_model.zip` | | | Ready-made complete model (Steps 1–12), unsupervised: 7-day `sum` window, scored every 12 hours |

## The data

| Property | Value |
|---|---|
| Assets | `AC-01` to `AC-12` (12 aircraft) |
| Asset column | `asset_id` |
| Log column | `maintenance_log`: free-text notes in maintenance shorthand |
| Timestamp column | `date`: date and time, `YYYY-MM-DD HH:MM:SS` |

The notes are written the way maintenance logs often are, with references to the maintenance manual (AMM), the minimum equipment list (MEL) and the crew alerting system (ECAM). For example:

- *"HYDRAULIC GREEN SYSTEM LOW PRESSURE caution on approach, cleared on ground"* (a pilot's report)
- *"Bleed 2 pressure regulating valve replaced IAW AMM 36-11-00, leak check good"* (a maintenance action)
- *"Deferred IAW MEL 21-xx, pack 1 inop, rectification within 5 days"* (a deferred defect)
- *"Corrosion found aft cargo floor beam STA 960, beyond SRM limits, engineering disposition requested"* (a finding in a check)

The labelling step finds the systems for itself. It uses an LLM, so the names and number of systems vary from run to run and with the numbers you choose, and a model you build will differ from the ready-made one. The notes cover these areas:

| Area | Example notes |
|---|---|
| Air conditioning | "Pack 2 flow control valve slow to open on BITE test" |
| Bleed air | "Bleed leak warning wing left on taxi in, cleared after 2 min" |
| Hydraulics | "Hydraulic engine driven pump 1 pressure fluctuating" |
| Landing gear and brakes | "BRAKE 3 HOT after landing, temp above normal, cooled on stand" |
| Auxiliary power unit | "Auxiliary power unit fails to start on first attempt, started on second" |
| Electrical | "Drive generator 2 oil temperature high indication during climb" |
| Fuel | "Fuel quantity indication fluctuating on wing tank right" |
| Engines | "ENGINE 1 VIBRATION high N1 in cruise" |
| Structures | "Crack found on cargo door frame STA 790, repair raised to engineering" |
| Cabin | "Lavatory aft flush inoperative, lav locked" |

**Signal design:**
- Aircraft `AC-04` and `AC-09` are older airframes with about twice the usual number of notes.
- Before each unscheduled visit, the same defect keeps coming back on the failing system, more often each day, over 14–21 days. These are repeat defects. The aircraft's overall note rate also doubles in the last 14 days.
- The visit itself is logged as an AOG note (aircraft on ground), followed by the repair and the release to service.
- Light A-checks every ~10 weeks add a night of cabin and servicing findings. Four heavy C-checks of about three weeks each fill the log with structural findings: `AC-03` (March 2023), `AC-08` (June 2023), `AC-10` (October 2023) and `AC-06` (15 January to 4 February 2024). Neither kind of check is followed by a failure, so they test that the model doesn't flag every busy period.

**Failures:** `failures.csv` has 24 unscheduled hangar visits on 7 aircraft. 20 are in the training period (2023) and 4 are in the new data: `AC-07` (7 Feb), `AC-09` (21 Feb), `AC-11` (2 Mar) and `AC-12` (23 Mar 2024). They come from bleed air, hydraulics, landing gear, electrical, fuel and engine defects. An inoperative APU or a single pack can usually be deferred under the MEL, so in this data those cause defects but not hangar visits.

With the ready-made model, AC-09 reaches the high band three days before its visit. AC-07 and AC-12 reach the watch band before theirs. AC-11's failure builds up in bleed air, which the labelling weighted low, so it rises but raises no alert.

## Notebook settings

Use the free-text notebooks with these settings. Also change the asset, system and subsystem names in the plot cells to ones from this data.

| Notebook | Settings |
|---|---|
| `01b_labelling_free_text.ipynb` | `FILE_PATH = "sample_data/aircraft_mro_hangar/training.csv"`, `ASSET_CONTEXT = "commercial narrow-body aircraft"`, `MAX_SYSTEMS = 10` (the ready-made model used these, with `MAX_SUBSYSTEMS = 4`) |
| `02c_risk_score_free_text_unsupervised.ipynb`, `02d_risk_score_free_text_supervised.ipynb` | `ZIP_PATH`, `TRAINING_FILE`, `GENERATION_FILE` (and the failures file for `02d`) in `sample_data/aircraft_mro_hangar/` |
| `03b_fleet_app_free_text.ipynb` | `MODEL` and `TRAINING` in `sample_data/aircraft_mro_hangar/`, and a deployment name of your own |

`how_to.md` at the top of the how-to folder explains how the weekly batches are cut.
