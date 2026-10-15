---
name: risk-score
description: >
  Guided agent intelligence for the Amygda Ops Risk Score SDK (v4.0.0).
  This skill teaches an LLM agent how to walk any user — technical or
  non-technical — through the full end-to-end pipeline: asking the right
  upfront questions, narrating each step in plain language, showing helpers
  with interpretive guidance, flagging irreversible steps, and handling
  session recovery. Covers all four user journeys (fixed/free-text ×
  supervised/unsupervised) and continuous scoring.
  Trigger on: "risk score", "amygda", "ops risk", "equipment risk",
  "predictive maintenance", "operational risk score", "asset risk", "amygda sdk".
license: MIT
compatibility: "SDK v4.0.0 — requires server API >= 3.0.1; Python >= 3.10"
metadata:
  version: "4.0.0"
  author: "Amygda"
---

# Amygda Ops Risk Score — Agent Guide

**Repo:** https://github.com/Amygda/amygda_ops_risk_score_sdk  
**SDK version:** 4.0.0 | **API minimum:** 3.0.1 | **Python:** ≥ 3.10

---

## AGENT GUIDANCE — READ THIS BEFORE DOING ANYTHING

You are acting as an expert guide for the Amygda Ops Risk Score pipeline. Your job is to walk the user through the process conversationally — asking the right questions, explaining what each step does in plain language, running each step, showing the output, and helping the user interpret it before moving on.

**Execute each pipeline step yourself using your tools — do not hand code blocks to the user to run.** You run the SDK code; the user sees the result and your interpretation of it. If you do not have code execution tools available, give the minimal code block and ask the user to paste back the output, then continue from there.

**Guide the user step by step in conversation — do not produce files for them to run.** Everything you need is in the `references/` files — load them as instructed below. Do not use the word "notebook" in any user-facing response.

**Do not run any pipeline step before asking the upfront questions in the relevant section below.** A non-technical user will not know what parameters to supply — you need to elicit them through conversation first.

Reference files (load on demand — each step below tells you which to load):
- `references/client.md` — OpsRiskClient methods (open_session, get_session, restart_session, wait_until_ready)
- `references/session.md` — Session pipeline methods (Steps 1–12)
- `references/helpers.md` — all helper/visualisation functions

The pipeline has two phases:

- **Labelling (Steps 1–8):** Upload logs → extract vocabulary → build equipment hierarchy with AI → classify every log entry → download the trained labelling model
- **Risk Score (Steps 9–12):** Load historical logs → calibrate risk thresholds → score new logs → download per-asset, per-day risk scores

Steps 8 and 12 are **ONE-WAY DOORS** — the server session is permanently deleted when they complete. Always warn the user before calling them.

---

## Installation — Do This First

```bash
pip install git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
# To upgrade an existing install:
pip install --upgrade git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
# Optional — VS Code kernel registration only:
pip install "amygda-ops-risk-score[ide]"
```

Confirm the install worked before proceeding:
```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig, helpers
```

---

## Deployment Modes — Choose Your Path First

Ask the user which mode they are on. The two paths have different prerequisites and API key types. **Do not ask about an Amygda API key if the user is on Local Docker.**

```
Which deployment mode are you using?
│
├── PATH A: Hosted API ──────────────────────────────────────────┐
│   Amygda manages infrastructure.                               │
│   • Need: Amygda API key                                       │
│   • Get one: email faizan@amygdalabs.com                       │
│   • SDK: OpsRiskClient()  ← no base_url needed                 │
│                                                                 │
└── PATH B: Local Docker ────────────────────────────────────────┐
    All data stays on your machine. You supply your own LLM key. │
    • Need: Docker Desktop 24+, 8 GB RAM free, port 8000 free    │
    • Need: Your own OpenAI or Anthropic API key (for .env)      │
    • Need: ~5 GB disk for the Docker image                      │
    • SDK: OpsRiskClient(base_url="http://localhost:8000")        │
```

---

## Session Start — PATH A (Hosted API)

```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig, helpers

client = OpsRiskClient()
client.wait_until_ready()     # handles cold start (60–120 s)

session = client.open_session(
    api_key="YOUR_AMYGDA_API_KEY",    # from faizan@amygdalabs.com
    config=SessionConfig(name="my-run"),
    artifact_dir="artifacts/my_run/",
)
```

---

## Session Start — PATH B (Local Docker)

Tell the user:

> "Follow the setup guide at `local_setup/README.md` in the SDK repo — it walks you through Docker, the `.env` file, and generating your local API key. Come back once you have a `demo-<hex>` key and the container is running."

Once they return with their key:

```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig, helpers

client = OpsRiskClient("http://localhost:8000")
client.wait_until_ready()     # blocks ~60–90 s on cold start

session = client.open_session(
    api_key="demo-<key-from-seed>",   # the demo-<hex> key generated by seed.py
    config=SessionConfig(name="my-run"),
    artifact_dir="artifacts/my_run/",
)
```

**Critical for local mode:** `artifact_dir` is not optional — all session data inside Docker is deleted when the pipeline completes. The JSON files saved in `artifact_dir` are the only copy of your step results.

From here, all pipeline steps (Steps 1–12) are identical to PATH A.

---

## Session Lifecycle — Four Scenarios

Every time a session starts, establish which scenario applies before running any step:

**Case 1 — Brand new session** (default): Create a fresh session with `open_session()`.

**Case 2 — Kernel restarted, server session still alive:** The server holds session state for up to 6 hours. Ask the user for their `AUTH_ID` (printed when the original session opened) and reconnect:
```python
session = client.get_session(auth_id="ses-xxxxxxxx", artifact_dir="artifacts/my_run/")
# Reload step results from saved JSON files in artifact_dir as needed
```

**Case 3 — Network dropped, kernel still running:** First check whether a long-running step completed during the outage:
```python
status = session.status()   # dict of step states
```
If the step is DONE, continue. If `session.status()` raises `APIError` with status 404, the session expired during the outage — call `open_session()` again; it auto-resumes if the server session is still alive, or creates a fresh one if not.

**Case 4 — Step is locked (need to go back):** Some steps lock out earlier ones. Use `restart_session()` to create a fresh session and re-run from the beginning:
```python
session = client.restart_session(session=session, api_key="YOUR_API_KEY", config=SessionConfig(name="retry"))
```
Note: one active session per API key. `restart_session` deletes the old one first.

The `next_step` field in every step response tells you exactly which method the server expects to be called next. Use it to confirm you are in sync with the server's state.

---

## PART 1 — LABELLING PIPELINE (Steps 1–8)

### Before You Begin — Ask the User These Questions

Before writing a single line of code, collect:

| Question | Why it matters |
|---|---|
| What is the **file path** to their log data? (CSV or XLSX) | Required for Step 1 |
| Which **column contains the log entries** — event codes or maintenance text? | `log_column` |
| Which **column identifies each asset/machine**? | `asset_column` |
| What **type of asset** is this? Give a specific description. | `asset_context` — sent to the AI to build the hierarchy. Quality matters. Bad: "industrial machine". Good: "rail vehicle HVAC unit for passenger cabin climate control" |
| Are the logs **structured event codes** (e.g. "EVT-001") or **free-form maintenance text** (e.g. "replaced bearing on unit 3")? | Sets `is_free_text` — affects the entire pipeline |
| How many **top-level systems** should the hierarchy have? (1–10, default 5) | `max_systems` |
| How many **subsystems per system**? (1–5, default 3) | `max_subsystems` |
| What **folder** should outputs be saved to? | `artifact_dir` |
| **PATH A only:** Do they have an Amygda API key? | Direct to faizan@amygdalabs.com if not |
| **PATH B only:** Is Docker Desktop running and local container set up? | See Session Start — PATH B above |

---

### Step Cycle Reference

| Step | Method | Repeatable? | Locked after |
|---|---|---|---|
| 1 | `configure_labelling_pipeline` | ✅ Yes | Step 2 or Step 3 starts |
| 2 | `downsample` | ✅ Yes — only if `downsample_required=True` | Step 3 starts |
| 3 | `extract_keywords` | ✅ Yes | Step 4 starts |
| 4 | `generate_hierarchy` | ✅ Yes | Step 5 or Step 6 starts |
| 5 | `update_hierarchy` | ✅ Yes — optional | Step 6 starts |
| 6 | `generate_weights` | ✅ Yes | Step 8 starts |
| 7 | `update_weights` | ✅ Yes — optional | Step 8 starts |
| 7b | `preview_classification` | ✅ Yes — optional | Step 8 starts |
| **8** | **`run_classification`** | **🚫 ONE-WAY DOOR** | **session wiped on completion** |

To go back past a lock: call `client.restart_session()` — this deletes all server-side data and restarts from Step 1 (Part 1) or re-imports the model (Part 2).

---

### Step 1 — Configure Labelling Pipeline

**What this does:** Uploads the log file to the server and stores the pipeline configuration. The server checks column names and counts rows. Nothing is classified yet — this is just setup.

**Call:** `result = session.configure_labelling_pipeline(file_path, log_column, asset_column, max_systems, max_subsystems, asset_context, is_free_text, sheet_name=None, *, timeout=600.0)`
**Returns:** `row_count`, `downsample_required`, `available_columns`, `is_free_text`, `next_step`

**What to check:** Look at `result.downsample_required`. If `True`, the dataset is too large for direct classification — Step 2 is needed. If `False`, skip to Step 3.

Also confirm `result.available_columns` lists the column names you expected. `result.next_step` tells you what to call next.

**STOP HERE — show the user:**
- [ ] `row_count` — unique log descriptions found (this is what the server will work with)
- [ ] `downsample_required` — if True, Step 2 is needed before Step 3; if False, skip straight to Step 3
- [ ] `is_free_text` — confirm this matches what the user intended (True = unstructured text, False = structured codes)

Then ask: "Does this look right? Correct column names, asset type, and free-text setting?"

---

### Step 2 — Downsample (Only if Step 1 said it's required)

**What this does:** Reduces the dataset to a manageable size by taking a representative sample — like selecting a good cross-section of your log history rather than every single entry. The sample preserves the distribution across your asset types.

**Call:** `result = session.downsample(sample_size, asset_column=None, vehicle_column=None, timestamp_column=None, *, file_path=None, sheet_name=None, timeout=600.0)`
**Returns:** `original_rows`, `sampled_rows`, `next_step`, `downsampled_path`
**Note:** At least one of `asset_column`, `vehicle_column`, `timestamp_column` must be provided; `file_path` and `sheet_name` are keyword-only.

More stratification columns → better-balanced sample. Add `timestamp_column` if you want the sample spread across time as well as assets.

**STOP HERE — show the user:**
- [ ] Load `downsampled.parquet` from `artifact_dir` and display the first 20 rows

Then ask: "Does this sample look like a representative selection of your log history?"

---

### Step 3 — Extract Keywords

**What this does:** Scans the log text and extracts the key terms that describe how your equipment behaves — words like "bearing", "temperature", "fault", "reset". These terms are what the AI uses in the next step to understand your system. Think of it as building a vocabulary from your data.

**Call:** `result = session.extract_keywords(extraction_method="fast", *, linguistic_filter=True, timeout=1200.0)`
**Returns:** `keywords`, `keyword_pool`, `finalised_keyword_count`, `next_step`

**Choosing the method:**
- Fixed-log (structured codes): use `"fast"`
- Free-text (maintenance notes): use `"deep"` — it handles abbreviations and domain terms better
- If your domain uses heavy jargon not in a standard dictionary, set `linguistic_filter=False`

**STOP HERE — show the user:**
- [ ] keyword cloud (`helpers.plot_keyword_cloud(...)`)
- [ ] top keywords bar chart (`helpers.plot_top_keywords(...)`)
- [ ] top keywords table (`helpers.get_top_keywords_table(...)`)

**Call:** `helpers.plot_keyword_cloud(keywords)` — word cloud of extracted keywords
**Call:** `helpers.plot_top_keywords(source)` — Plotly bar chart, top keywords by frequency
**Call:** `helpers.get_top_keywords_table(source)` — returns DataFrame with `["Keyword", "Frequency"]`

Then ask: "Do these terms look like they describe how your equipment works? Are any important terms missing? Are there noise terms you'd want removed?"

If the vocabulary looks wrong, try switching `extraction_method` or `linguistic_filter` and re-running Step 3 (can be re-run until Step 4 starts).

---

### Step 4 — Generate Hierarchy

**What this does:** Sends the extracted keywords to the AI, which groups them into a two-level map of your equipment: top-level **systems** (e.g. "Drive System", "Electrical") and **subsystems** within each (e.g. "Motor", "Belt", "Control Board"). This hierarchy is the backbone of all risk scoring — it determines how logs are classified and how risk is aggregated.

This is an AI call and takes 30 seconds to 3 minutes.

**Call:** `result = session.generate_hierarchy(*, keywords=None, timeout=1200.0)`
**Returns:** `hierarchy`, `systems_count`, `subsystems_count`, `keywords_source`
**Note:** `keywords=None` uses the pool from `extract_keywords`; `extract_keywords` must be completed first regardless.

Each row in the hierarchy has a **confidence rating** (high / medium / low) that reflects how strongly the keyword evidence supports the classification:
- 🟢 High — strong keyword evidence
- 🟡 Medium — moderate evidence, worth reviewing
- 🔴 Low — weak evidence, AI is guessing — these rows most likely need editing

**STOP HERE — this is the main human judgement gate.**

Show the user:
- [ ] hierarchy tree colour-coded by confidence (`helpers.plot_hierarchy(result)` — sunburst: inner ring = systems, outer ring = subsystems, coloured by confidence)

Then ask:
- "Does this hierarchy match how you think about your equipment?"
- "Are the system names meaningful to your team?"
- "Are any important systems missing? Are any wrong?"
- "Any subsystems that are in the wrong group?"

If they want to edit, proceed to Step 5. If it looks right, go to Step 6.

Hierarchy can be regenerated until `update_hierarchy` or `generate_weights` starts.

---

### Step 5 — Refine Hierarchy (Optional, Repeatable)

**What this does:** Lets you correct the AI's hierarchy — rename systems, add/remove subsystems, adjust confidence levels. This completely replaces the AI-generated version with your edited one.

**Two ways to edit:**

**Option A — CSV round-trip (recommended for larger hierarchies):** Call `helpers.hierarchy_to_csv(...)` to export, let the user edit in Excel or Numbers, then call `helpers.hierarchy_from_csv(...)` to import and `session.update_hierarchy(rows=rows)` to apply.

**Call:** `csv_path = helpers.hierarchy_to_csv(result, path)` — `result` accepts dict or file path; returns absolute CSV path
**Call:** `rows = helpers.hierarchy_from_csv(path)` — returns validated rows ready for `update_hierarchy`
**Call:** `result = session.update_hierarchy(rows, *, timeout=1200.0)`
**Returns:** `hierarchy`, `systems_count`, `subsystems_count`, `next_step`

**Option B — Edit directly in Python:** Call `helpers.make_hierarchy_rows(result)` to convert to editable flat format, edit the rows list, then `session.update_hierarchy(rows=rows)`.

**Call:** `rows = helpers.make_hierarchy_rows(result)` — accepts result dict only (not file path); returns editable deep copy
**Call:** `result = session.update_hierarchy(rows, *, timeout=1200.0)`
**Returns:** `hierarchy`, `systems_count`, `subsystems_count`, `next_step`
**Note:** Each row must have keys `system`, `system_confidence`, `subsystem`, `subsystem_confidence`; confidence values must be `"high"`, `"medium"`, or `"low"`.

**Validation rules (enforced automatically):**
- Every row needs all four keys: `system`, `system_confidence`, `subsystem`, `subsystem_confidence`
- `system_confidence` must be the same value for all rows belonging to the same system
- Confidence values must be `"high"`, `"medium"`, or `"low"`
- No duplicate (system, subsystem) pairs
- System and subsystem names must be non-blank strings

After updating, view the result: `helpers.plot_hierarchy(result)` — sunburst chart coloured by confidence. Can be repeated as many times as needed before Step 6.

**Note:** If a system you added does not appear when weights are generated (Step 6), it means the log data had no keyword evidence for it. That is a normal, data-driven outcome.

---

### Step 6 — Generate Weights

**What this does:** Locks in the current hierarchy and assigns **criticality weights** to each system and subsystem. Weights determine how much each system contributes to the overall operational risk score — a higher weight means that system's activity drives the risk number more strongly.

**Call:** `result = session.generate_weights(*, timeout=300.0)`
**Returns:** `weights`, `systems_count`, `next_step`

**STOP HERE — show the user:**
- [ ] weights chart (`helpers.plot_weights(result)` — two-panel bar chart: system weights left, subsystem weights right)

Then ask: "Do these weights feel right? Is there a system that's more critical to your operations that should be weighted higher? Or one that matters less?"

Weights can be adjusted in Step 7. Can be regenerated until `run_classification` starts.

---

### Step 7 — Refine Weights (Optional, Repeatable)

**What this does:** Lets you override the generated weights. The system auto-normalises — you only need to change the values you care about, and the rest will be scaled proportionally to fill the remaining budget. You never need to make the numbers add up to 1.0 manually.

**Two ways to edit:**

**Option A — CSV round-trip:** Call `helpers.weights_to_csv(...)` to export, let the user edit, then `helpers.weights_from_csv(...)` to import and `session.update_weights(...)` to apply.

**Call:** `csv_path = helpers.weights_to_csv(result, path)` — exports flat CSV with `system_name`, `system_weight`, `subsystem_name`, `subsystem_weight`
**Call:** `systems = helpers.weights_from_csv(path)` — returns systems list compatible with `update_weights(systems=...)`
**Call:** `result = session.update_weights(systems, *, original_systems=None, timeout=1200.0)`
**Returns:** `weights`, `systems_count`, `next_step`
**Note:** Pass `original_systems` (from `generate_weights` or a prior `update_weights`) to enable name-change protection.

**Option B — Edit directly in Python:** Call `helpers.make_weight_update(result)`, edit the list, then `session.update_weights(...)`.

**Call:** `systems = helpers.make_weight_update(result)` — accepts result dict only; returns editable deep copy with keys `system_name`, `weight`, `subsystems`
**Call:** `result = session.update_weights(systems, *, original_systems=None, timeout=1200.0)`
**Returns:** `weights`, `systems_count`, `next_step`

**Important rules when editing the CSV:**
- `system_weight` must be the same value across every row of the same system — if you raise the system weight, update every row for that system
- Do NOT rename `system_name` or `subsystem_name` columns or values
- Do NOT change row order

After updating, view the result: `helpers.plot_weights(result)` — two-panel bar chart. Can be repeated as many times as needed before Step 8.

---

### Step 7b — Check Coverage Before Committing (Recommended)

**What this does:** Tests how many of your logs and assets would be classified at different confidence thresholds — before you commit to the irreversible Step 8. Think of it as a dry run: "if I set the threshold here, how much of the data gets matched?"

**Important:** The first call takes about 1 minute (builds the search index and finds the optimal threshold). Every subsequent call is instant because the index is cached.

**Call:** `result = session.preview_classification(threshold=0.4, *, timeout=1800.0)`
**Returns:** `optimal_threshold`, `assets_covered`, `total_assets`, `logs_classified`, `total_logs`, `coverage_by_asset`, `classification_by_log`

**Key things to check in the result:** `optimal_threshold`, `assets_covered`, `total_assets`, `logs_classified`, `total_logs`, `coverage_by_asset` (a per-asset breakdown), and `uncovered_assets`.

`optimal_threshold` is the highest threshold that still maximises how many assets are covered. It is automatically used in Step 8 if you do not override it.

**STOP HERE — ask the user:**
- "These are the assets where no logs were matched: [list uncovered_assets]. Is that expected, or should those assets have been covered?"
- "If coverage looks too low, try adjusting the threshold and re-running Step 7b — it can be repeated as many times as needed before Step 8. Note: Step 3 (keyword extraction) is locked once Step 4 has run, so the keyword vocabulary cannot be changed from here. If the keywords themselves need to change, the only way back is `client.restart_session()`, which deletes all session data and restarts from Step 1."

**Note for fixed-log sessions:** The similarity threshold has no effect on actual classification (fixed codes are matched exactly, not by similarity). The coverage stats are still useful for a sanity check, but the threshold value doesn't change classification outcomes.

Can be re-run as many times as needed before Step 8.

---

### Step 8 — Run Classification ⚠️ ONE-WAY DOOR

**⚠️ WARN THE USER BEFORE CALLING THIS STEP.**

Say: *"This next step will classify every log entry in your dataset and produce the final labelling model. Once I run it, the server session is permanently deleted — there is no undo. The results are downloaded as a zip file to your machine. Are you ready to proceed?"*

**What this does:** Classifies every log entry against the hierarchy, builds the final model, downloads it as a zip file, then permanently deletes the server session.

**Call:** `result = session.run_classification(dest_dir, similarity_threshold=None, *, timeout=3600.0)`
**Returns:** `zip_path`, `total_rows`, `similarity_threshold_used`, `threshold_source`

**Recovery note:** The session is only deleted after a successful download. If the download fails, the session is still alive and you can retry by calling `run_classification()` again — it skips re-running classification and goes straight to re-downloading.

**After this step — show the user:**
- [ ] Load `deduplicated_predictions.parquet` from the zip
- [ ] stacked classification chart (`helpers.plot_classification_stacked(...)`)
- [ ] classification by system (`helpers.plot_classification_by_system(...)`)
- [ ] classification by subsystem (`helpers.plot_classification_by_subsystem(...)`)

**Call:** `helpers.plot_classification_stacked(source)` — stacked bar: x=system, stacked by subsystem, y=log count
**Call:** `helpers.plot_classification_by_system(source)` — bar chart of log count per system
**Call:** `helpers.plot_classification_by_subsystem(source, top_n=20)` — horizontal bar, top N subsystems by log count

These charts show how logs were distributed across the hierarchy. Then ask: "Does this distribution look reasonable? Does the proportion of logs in each system match your expectation of where most activity happens?"

**If the classification looks wrong:** Inspect the charts to understand the distribution. Step 8 is a one-way door — the server session has been permanently deleted and there is no undo. To redo the labelling from scratch, open a new session with `client.open_session()` and re-run from Step 1.

**Save the zip file carefully** — it is needed to start the risk scoring pipeline (Part 2).

---

## PART 2 — RISK SCORE PIPELINE (Steps 9–12)

### Pipeline Hand-off

The risk score pipeline starts from the labelling model zip produced in Step 8. The SDK can also auto-read `api_key.txt` and `run_classification.json` from `LABELLING_ARTIFACT_DIR` — so if the user ran Part 1 into a known folder, all they need to supply is that folder path.

Open a new session with `client.open_session(...)`, then call `session.import_model(zip_path)` to load the labelling model zip.

**Call:** `session = client.open_session(api_key, config, artifact_dir=None)`
**Call:** `result = session.import_model(zip_path, *, timeout=600.0)`
**Returns:** `is_free_text`, `risk_training_restored`, `next_step`, `log_column`
**Note:** Pass labelling zip to unlock Steps 9–12; pass complete model zip to set `risk_training_restored=True` and unlock Step 11 directly.

Also accepts a `complete_model_ses-xxx.zip` from a prior `generate_risk_scores` run. Importing a complete model zip unlocks Step 11 directly — skips Steps 9–10 entirely.

---

### Before You Begin — Ask the User These Questions

| Question | Variable |
|---|---|
| Where is the **historical log file** to train on? (Same column structure as labelling data) | `TRAINING_FILE` |
| Which column is the **asset ID**? | `ASSET_ID_COLUMN` |
| Which column is the **timestamp/date**? | `TIMESTAMP_COLUMN` |
| What is the **rolling window** in days? (1–30, default 7) — How many days of log history to aggregate per asset | `ROLLING_WINDOW` |
| What **rolling feature type**? For free-text: `"sum"` or `"flag"` only. For fixed-log: also `"ewm"` or `"all"`. Default `"sum"`. | `ROLLING_FEATURE_TYPE` |
| Do they have **failure records**? (A file listing when each asset failed) | Determines `SUPERVISED` |

**If supervised (they have failure records), also ask:**

| Question | Variable |
|---|---|
| Where is the **failures file**? | `FAILURES_FILE` |
| Which column has the **failure date**? | `FAILURE_DATE_COLUMN` |
| How many days **before a failure** should logs be labelled as "pre-failure risk"? | `PREDICTION_HORIZON_DAYS` |
| How many days **after a failure** should be excluded? (Recovery/settling period) | `EXCLUSION_DAYS_AFTER` |

---

### Supervised Parameter Design Guidance

If the user is running supervised mode, help them choose `PREDICTION_HORIZON_DAYS` and `EXCLUSION_DAYS_AFTER` thoughtfully — these are not arbitrary numbers.

**Six things to consider:**

1. **Inter-failure gap:** If failures on the same asset happen frequently, a long `PREDICTION_HORIZON_DAYS` means one failure's window can overlap the next — reducing the positive examples available for training. Check: what is the typical gap between failures on the same asset?

2. **Operational lead time:** How far in advance would advance warning actually be useful? A 14-day horizon means "we want to know 2 weeks ahead". A 7-day horizon means "a week's notice is enough".

3. **Recovery period:** After a repair, logs often look abnormal while the machine settles back in. `EXCLUSION_DAYS_AFTER` should cover this settling period so recovery logs don't get mislabelled as normal.

4. **Log density:** `ROLLING_WINDOW` needs enough log entries per asset-day that the rolling feature isn't mostly zeros. Sparse logs may need a longer window.

5. **Window ordering rule:** Keep `rolling_window ≤ prediction_horizon_days` — if the feature window extends beyond the prediction horizon, it reads data from outside the period you're trying to predict.

6. **Check the resulting balance:** After Step 10 runs, inspect `n_positive_rows` in the training report. If positives are very few, consider reducing `prediction_horizon_days` (shorter window, fewer conflicts) or lowering `min_positives`.

---

### Step Cycle Reference

| Step | Method | Repeatable? | Locked after |
|---|---|---|---|
| 9 | `configure_training` | ✅ Yes | Step 10 starts |
| 10 | `train_risk_model` | ✅ Yes | Step 11 starts |
| 11 | `configure_generation` | ✅ Yes | Step 12 starts |
| **12** | **`generate_risk_scores`** | **🚫 ONE-WAY DOOR** | **session wiped on completion** |

To go back past a lock: call `client.restart_session()` — this deletes all server-side data and restarts from Step 1 (Part 1) or re-imports the model (Part 2).

---

### Step 9 — Configure Training

**What this does:** Uploads the historical log file and stores the configuration for how risk features are calculated. The training file can be the same as the labelling file — it just needs the same column structure.

**Call:** `result = session.configure_training(file_path, asset_id_column, timestamp_column, date_format="infer", rolling_window=7, rolling_feature_type="sum", quantile_for_thresholds=0.99, sheet_name=None, supervised=False, failures_path=None, failure_date_column="machine_initialisation_date", prediction_horizon_days=14, exclusion_days_after=7, *, timeout=600.0)`
**Returns:** `row_count`, `asset_count`, `is_free_text`, `supervised`, `next_step`
**Note:** `rolling_feature_type` `"ewm"` and `"all"` are fixed-log only; `failures_path` is required when `supervised=True`.

Can be re-run until `train_risk_model` starts.

---

### Step 10 — Train Risk Model

**What this does:** Runs the model training. For unsupervised mode, it fits a calibration threshold for each subsystem based on the historical distribution — the threshold defines what "elevated activity" looks like. For supervised mode, it additionally learns which subsystems were most predictive of failures and adjusts the weights accordingly.

**Call:** `result = session.train_risk_model(*, timeout=3600.0)`
**Returns:** `subsystems_calibrated`, `supervised`, `thresholds_path`, `training_fe_path`, `training_scores_path`

**Free-text note:** The `similarity_threshold` baked into the labelling model zip is used automatically during training and generation — you do not need to pass it again.

**Artifacts downloaded:**

| File | Always? | What it contains |
|---|---|---|
| `calibration_thresholds.json` | Yes | Per-subsystem threshold values |
| `training_fe.parquet` | Yes | Rolling features per asset/date/subsystem |
| `training_scores.parquet` | Yes | Risk scores on historical training data |
| `logs_by_system_subsystem.json` | Fixed-log only | Code → subsystem mapping |
| `supervised_training_report.json` | Supervised only | AUC-ROC, average precision, counts |
| `trained_weights.json` | Supervised only | Learned subsystem weights |

**STOP HERE — show the user:**
- [ ] calibration thresholds chart (`helpers.plot_calibration_thresholds(thresholds_source, training_fe_source)` — overlaid bar: max, mean, threshold per subsystem)

Each bar shows: calibrated threshold vs mean and max of the training distribution for that subsystem.

**Threshold sanity check:**
- 🔴 **Threshold near the mean:** Too aggressive — this subsystem will almost always be flagged as elevated, even in normal operation. Consider raising `quantile_for_thresholds`.
- 🔴 **Threshold near the maximum:** Unreachably high — this subsystem will rarely or never trigger. Consider lowering `quantile_for_thresholds`.
- 🟢 **Threshold clearly above mean but below max:** Good calibration.

For feature distributions, feature-over-time, and full pipeline view, also show:
- [ ] feature distributions (`helpers.plot_training_feature_distributions(...)`)
- [ ] features over time (`helpers.plot_training_feature_over_time(...)`)
- [ ] subsystem pipeline view (`helpers.plot_subsystem_feature_pipeline(...)`)

**Call:** `helpers.plot_training_feature_distributions(training_fe_source, thresholds_source)` — histogram grid per subsystem with threshold line
**Call:** `helpers.plot_training_feature_over_time(training_fe_source, thresholds_source, asset_id, system, subsystem)` — time series for one asset/subsystem
**Call:** `helpers.plot_subsystem_feature_pipeline(training_fe_source, thresholds_source, asset_id, system, subsystem, is_free_text=True)` — 3-panel chart; pass `logs_mapping` when `is_free_text=False`

**If supervised — additional visualisations:**
- [ ] label timeline (`helpers.plot_label_timeline(...)`)
- [ ] label distribution (`helpers.plot_label_distribution(...)`)
- [ ] supervised comparison (`helpers.plot_supervised_comparison(...)`)
- [ ] weight comparison (`helpers.plot_weight_comparison(...)`)
- [ ] risk around failures (`helpers.plot_risk_around_failures(...)`)
- [ ] failure risk stats (`helpers.plot_failure_risk_stats(...)`)

**Call:** `helpers.plot_label_timeline(feature_source, failures_source)` — per-asset label zones (normal, pre-failure, excluded)
**Call:** `helpers.plot_label_distribution(feature_source, failures_source)` — positive vs negative row counts over time
**Call:** `helpers.plot_supervised_comparison(report_source)` — grouped bar: baseline vs supervised AUC-ROC and Avg Precision
**Call:** `helpers.plot_weight_comparison(expert_source, trained_source)` — expert vs trained weights at system or subsystem level
**Call:** `helpers.plot_risk_around_failures(risk_source, failures_source)` — risk time series per failing asset with failure markers
**Call:** `helpers.plot_failure_risk_stats(risk_source, failures_source)` — box plot: pre-failure vs normal risk distribution

**If fixed-log + supervised — detection performance analysis:**

Note: `plot_detection_roc` returns the threshold value, which must be passed to the next two calls. Call them in sequence:
- [ ] `helpers.plot_detection_roc(...)` — captures the detection threshold
- [ ] `helpers.plot_failure_detection_summary(threshold)` — pass the threshold from the previous call
- [ ] `helpers.plot_failure_detection_timeline(threshold)` — pass the threshold from the previous call

**Call:** `threshold = helpers.plot_detection_roc(risk_source, failures_source)` — returns float; ROC curve + Youden's J chart
**Call:** `helpers.plot_failure_detection_summary(risk_source, failures_source, detection_threshold=threshold)` — per-failure audit table
**Call:** `helpers.plot_failure_detection_timeline(risk_source, failures_source, detection_threshold=threshold)` — timeline coloured by detection outcome

---

### Step 11 — Configure Generation

**What this does:** Uploads the new log file to score — the data you want to get risk scores for. This can be the same file as training (to score the historical period) or newer data.

The `weights_source` parameter determines which weights are used to combine subsystem scores into the overall operational risk:

| `weights_source` | When to use |
|---|---|
| `"labelling"` | Always valid — uses expert weights from the labelling phase |
| `"supervised"` | Only valid after supervised training — uses weights learned from failure patterns |

Rule: `weights_source = "supervised" if SUPERVISED else "labelling"`. Passing `"supervised"` after an unsupervised training run will return an API error.

**Call:** `result = session.configure_generation(file_path, date_format="infer", sheet_name=None, weights_source="labelling", *, timeout=600.0)`
**Returns:** `row_count`, `asset_count`, `weights_source`, `next_step`
**Note:** `weights_source="supervised"` is only valid after `configure_training(supervised=True)` + `train_risk_model()`.

Can be re-run until `generate_risk_scores` starts.

---

### Step 12 — Generate Risk Scores ⚠️ ONE-WAY DOOR

**⚠️ WARN THE USER BEFORE CALLING THIS STEP.**

Say: *"This step will score every log entry and produce the final per-asset, per-day risk scores. Once I run it, the server session is permanently deleted. The full model and all results are downloaded to your machine. Are you ready to proceed?"*

**What this does:** Scores every log entry against the trained model, generates risk scores for each asset for each day, downloads the complete model zip, extracts all artifacts, then permanently deletes the server session.

**Call:** `result = session.generate_risk_scores(dest_dir, *, timeout=3600.0)`
**Returns:** `zip_path`, `assets_scored`, `date_range`, `parquet_path`

**What is downloaded and extracted:**

| File | What it contains |
|---|---|
| `complete_model_ses-xxx.zip` | Full trained model — re-import for future scoring without retraining |
| `risk_scores.parquet` | **Primary output:** per-asset, per-day risk scores |
| `classified_logs.parquet` | Per-log classification *(free-text mode only)* |
| `logs_by_system_subsystem.json` | Code → subsystem mapping *(fixed-log only)* |
| `calibration_thresholds.json` | Per-subsystem threshold values |
| `accepted_hierarchy.json` | The final hierarchy used |
| `model_config.json` | System and subsystem weights |

**Re-scoring future data without retraining:** Import `complete_model.zip` in a new session via `session.import_model(zip_path)` (`risk_training_restored=True` in the result confirms thresholds were restored), then go straight to Step 11 — Steps 9–10 are skipped entirely.

---

### After Step 12 — Explore the Risk Scores

**STOP HERE — generation complete. Show the user:**
- [ ] `assets_scored` — how many assets received risk scores
- [ ] `date_range` — the time period covered

Then proceed to the visualisations below.

**Fleet-level overview:** Load `risk_scores.parquet` then call:
- [ ] `helpers.plot_asset_risk_ranking(...)`
- [ ] `helpers.plot_risk_score_distribution(...)`
- [ ] `helpers.list_risk_metrics(...)` — returns available column names, e.g. `["operational_risk", "drive_system_system_risk", ...]`

**Call:** `helpers.plot_asset_risk_ranking(source)` — bar chart sorted highest-first, green-to-red gradient
**Call:** `helpers.plot_risk_score_distribution(source)` — histogram of risk scores across all records
**Call:** `metrics = helpers.list_risk_metrics(source)` — returns `["operational_risk", ...]` for use with `plot_risk_heatmap`

**Fleet heatmap — assets over time:** `helpers.plot_risk_heatmap(source, metric="operational_risk")` — rows=assets, cols=dates; `metric` accepts `"operational_risk"` or any `{system}_system_risk` column.

**Single-day snapshot — all assets on one day:** `helpers.plot_daily_risk_snapshot(source, date)` — tile panel, one per asset; colour: blue (0–33), yellow (33–66), red (66–100); closest available date used if exact date not found.

**Single asset deep-dive — how risk evolved over time:**
- [ ] `helpers.plot_asset_risk_over_time(...)` (raw or `weighted=True`)
- [ ] `helpers.plot_system_contributions(...)` — stacked area chart showing each system's weighted contribution plus the overall risk line; bands widening before a known event signal early predictive warning
- [ ] `helpers.plot_asset_system_over_time(...)`

**Call:** `helpers.plot_asset_risk_over_time(source, asset_id, model_config=None, weighted=False)` — heatmap: risk types × dates for one asset; `model_config` required when `weighted=True`
**Call:** `helpers.plot_system_contributions(source, asset_id, model_config)` — stacked bar with operational risk line on top
**Call:** `helpers.plot_asset_system_over_time(source, asset_id, system)` — heatmap: system risk + subsystems × dates

**Drill into a specific subsystem — what logs triggered it:** For fixed-log sessions: `helpers.plot_subsystem_log_activity(source, asset_id, system, subsystem, date)` — bar chart of log occurrences; pass `logs_mapping` and `is_free_text=False` for fixed-log mode. For free-text sessions: `df = helpers.get_logs_for_subsystem(source, asset_id, system, subsystem, date)` — returns DataFrame of actual log text; `source` is `classified_logs.parquet`.

**If supervised — check if the model predicted failures in the generation period:**
- [ ] `helpers.plot_risk_around_failures(...)`
- [ ] `helpers.plot_failure_risk_stats(...)`

**Call:** `helpers.plot_risk_around_failures(risk_source, failures_source)` — multi-subplot time series per failing asset with failure markers
**Call:** `helpers.plot_failure_risk_stats(risk_source, failures_source)` — box plot: pre-failure vs normal risk distribution

**If fixed-log + supervised — detection analysis on scored data (generation period):** Same chain as training period, in sequence:
- [ ] `helpers.plot_detection_roc(...)` — captures the detection threshold
- [ ] `helpers.plot_failure_detection_summary(threshold)` — pass the threshold from the previous call
- [ ] `helpers.plot_failure_detection_timeline(threshold)` — pass the threshold from the previous call

**Call:** `threshold = helpers.plot_detection_roc(risk_source, failures_source)` — returns float; ROC curve + Youden's J chart
**Call:** `helpers.plot_failure_detection_summary(risk_source, failures_source, detection_threshold=threshold)` — per-failure audit table
**Call:** `helpers.plot_failure_detection_timeline(risk_source, failures_source, detection_threshold=threshold)` — timeline coloured by detection outcome

---

## Journey Reference — Which Steps and Helpers Apply

| | Fixed + Unsupervised | Fixed + Supervised | Free-text + Unsupervised | Free-text + Supervised |
|---|:---:|:---:|:---:|:---:|
| Example reference | 02b | 02a | 02c | 02d |
| `rolling_feature_type` | sum/flag/ewm/all | sum/flag/ewm/all | sum/flag only | sum/flag only |
| `classified_logs.parquet` | No | No | Yes | Yes |
| `get_logs_for_subsystem` | No | No | Yes | Yes |
| `logs_by_system_subsystem.json` | Yes | Yes | No | No |
| `weights_source` | labelling | supervised | labelling | supervised |
| `trained_weights.json` | No | Yes | No | Yes |
| Supervised vis after Step 10 | No | Yes | No | Yes |
| Detection ROC/summary/timeline | No | Yes (both) | No | No |
| Training failure evaluation | No | Yes | No | Yes |
| Post-generation failure section | No | Yes | No | Yes |

**Continuous scoring (5th journey):** Import `complete_model.zip` → call `configure_generation` (Step 11) directly → `generate_risk_scores` (Step 12). Steps 9–10 are skipped entirely.

---

## Quick-Start Checklist

- [ ] API key obtained (email faizan@amygdalabs.com)
- [ ] Python 3.10+ environment, SDK installed
- [ ] Log CSV/XLSX has: log column, asset ID column, timestamp column
- [ ] `asset_context` written — specific plain-English description of the asset type
- [ ] `is_free_text` set correctly (structured codes vs maintenance prose)
- [ ] `artifact_dir` folders exist and are writable before calling Steps 8 and 12
- [ ] Labelling zip saved after Step 8 — needed to start the risk score pipeline
- [ ] (Supervised) Failures CSV prepared with asset ID + failure date column
