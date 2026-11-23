# Deploy and Monitor

Use this for the deployment half of the fleet app (`app.md`): the model is **deployed** once, then new logs are scored without a session or retraining. The `amygda-risk` monitor keeps a folder on the user's machine with the history, every score, a record of each run and the page, and updates them each time new data arrives.

**The fleet app is how a user keeps scoring new data.** `app.md` has the questions, the layout, the alerts, the schedule and the steps in order; it sends you here for the deployment and the checks. There is no separate "scheduled scoring only" setup: don't offer one, and don't write cron, launchd or Task Scheduler entries that run the monitor. The app has the schedule.

**Setting up scores nothing.** Deploy, create the folder, check the deployment and stop. The user's data goes in through the app.

## Contents
- When to offer it
- Starting from an existing model zip
- Questions to ask
- Before deploying: codes the model doesn't use
- Steps
- Checks before handing over
- Loading older files
- Reading a run
- Troubleshooting
- Without deployments

---

## When to offer it

- **After Step 12**, once the "After Step 12" checks are done, offer the fleet app (`app.md`, "When to offer it"). Offer it only for a run the user is happy with: the checks passed and the alert bands are agreed. If the run needs more work, say so and offer it later.
- **When the user brings a `complete_model_<id>.zip`** and asks to deploy it, monitor with it or score new data: do the short path below, then `app.md`.

## Starting from an existing model zip

Nothing from Step 12 was seen in this conversation, so confirm the basics before deploying:

1. **It's a complete model.** The zip has `risk_score/training_scores.parquet` and `risk_score/risk_scores.parquet` (from Step 12). A labelling zip (Steps 1–8 only) can't be deployed: it needs Steps 9–12 first.
2. **What it is.** Read `outputs/model_config.json` and `risk_score/risk_score_config.json` and tell the user: fixed-log or free-text, supervised or unsupervised, how often it scores (`feature_frequency`) and the rolling window.
3. **Codes the model doesn't use** (next section but one).
4. **Bands.** Ask whether watch and high levels were agreed for this model. If not, explain the default before using it: *"Without agreed levels, the monitor sets watch at the 95th and high at the 99th percentile of the model's own training scores: here watch X and high Y. That means about 1 in 20 periods from normal operation reach watch and 1 in 100 reach high. They don't come from failures, so treat them as a starting point."* Read X and Y from the zip's `risk_score/training_scores.parquet`: the 0.95 and 0.99 quantiles of `operational_risk`, rounded to 1 decimal place. For a supervised model, offer to check them against failures first (`validation.md` → "Checking alert bands against failures").
5. **History.** Ask for earlier logs from just before the first new file (the training file if the new data follows it). Without them, the first `lookback` of scores is low.

Then carry on with the questions in `app.md`, skipping what's already answered.

## Questions to ask

Ask these with Round 3 in `app.md`. Say what the default is for each. The name, the folder, the schedule and how files arrive are settled there; don't ask them again.

| Question | Default |
|---|---|
| Which alert bands should it keep? | The watch and high levels agreed after Step 12. If none were agreed, the 95th and 99th percentile of the model's training scores (explain this, as above) |
| Which earlier logs can it use as history? | The Step 9 training file |

Don't ask about self-hosting: it isn't available yet. If the user asks, say a self-hosted scorer is coming soon.

If the user asks what deploying stores: a small scoring bundle (the model's structure, weights, thresholds and log codes or keywords; no log rows, asset IDs or timestamps) is kept on Amygda's servers until they delete the deployment or it goes unused for 90 days. Logs sent for scoring aren't kept. The SDK README has the details. Don't turn this into a question the user has to answer.

## Before deploying: codes the model doesn't use

For a fixed-log model, list the log codes its training data has that map to no subsystem. Logs with these codes never affect a score.

```python
from amygda_ops_risk_score import helpers
u = helpers.unmapped_codes("<complete_model.zip>")   # None for free-text
```

If `u["unmapped_share"]` is above 5%, show the user `u["top"]` as a table (code, training logs, share) and ask: *"These codes count for nothing in the score. Do any of them matter, for example a motor or bearing fault? If so, it's worth adding them to the hierarchy and retraining before deploying."* Go ahead only when the user is happy. If they can't judge or say "whatever you recommend": when the model came from this conversation, recommend fixing the hierarchy first if a listed code is clearly a fault (a motor, bearing or overtemperature code, say). When they only have the zip and can't retrain now, recommend going ahead, name the codes as a known gap (they show on the dashboard's Model tab), and suggest they raise it with whoever built the model. `amygda-risk init` repeats this as a warning, keeps the list in `monitor.json` (`model_checks`), and the dashboard's Model tab shows it.

For free-text models there is no code list. The first run's unmatched share is the signal instead (see "Reading a run").

## Steps

These are steps 3 and 4 of `app.md`. Run them yourself, one at a time, showing the output (see `agent-execution.md`). The API key comes from the environment as `AMYGDA_API_KEY`, or from a `.env` file the user made in the monitor folder or the folder above it, which the commands read themselves. Never pass the key on the command line, print it or write it to a file. Each command waits for the API if it is starting up (up to 15 minutes), so the first call after a quiet spell can take a minute or two.

1. **Create the monitor.** This deploys the model and creates the folder. It scores nothing:
   ```bash
   amygda-risk init <folder> --model <complete_model.zip> --name <name-v1> \
       --history <training_file> --fleet-name "<name>" [--watch <w> --high <h>]
   ```
   The folder, `--name` and `--fleet-name` come from the name the user chose (`app.md`, Round 2). Give `--watch` and `--high` when bands were agreed. Without them the monitor takes the 95th and 99th percentile of the model's training scores and says so in `monitor.json` (`bands.basis`). Use `--date-format` only if new files write dates differently from the training file. Pass on any `!` warning it prints.
2. **Check the deployment** (see "Checks before handing over", first item).
3. **Go back to `app.md`**, step 4: apply the layout, start the app, hand over. Don't score a file.

From Python the same step is `Monitor.init(path, model=..., name=..., history=..., bands=...)` (`from amygda_ops_risk_score.monitor import Monitor`). For a one-off score without a monitor, use `client.deploy_model` and `client.score` (`client.md`).

## Checks before handing over

- **The deployment scores exactly like Step 12.** Run:
  ```python
  import os
  from amygda_ops_risk_score import OpsRiskClient, helpers
  from amygda_ops_risk_score.monitor import Monitor
  mon = Monitor("<folder>")
  client = OpsRiskClient(mon.config.get("api_url"))        # the API the monitor uses
  api_key = os.environ[mon.config["api_key_env"]]          # from the environment; never print it
  helpers.check_deployment(client, api_key, mon.deployment["deployment_id"], "<complete_model.zip>")
  ```
  It scores the generation data saved in the zip, in one call with no history like Step 12, and compares every period with the zip's `risk_scores.parquet`. Expect `match: True` and `max_abs_diff` 0.0. If not, stop and report it to Amygda with the result.
  - **Don't compare the monitor's scores with Step 12.** The monitor adds earlier history (`--history`) before the first file, and Step 12 had none, so the monitor's scores for the first `lookback` of data are legitimately different, often higher (by up to 20 points in testing). After that they agree. Say this if the user compares them.
- **History was seeded.** `init` was given `--history`, so the user's first run has its `lookback` of earlier logs. If their first run still warns "Less than … of history", seed more (re-create the monitor with a longer `--history` file).
- **The bands are the agreed ones**, or the user has heard how the defaults were set: `bands` in `monitor.json`, with a `basis` the user would recognise.
- Tell the user where everything is: the folder, `inbox/` for new files, and `runs/` for the run records (with database storage, `monitor.db` holds the scores and run records instead: `app.md`, "Changing it later").

## Loading older files

Only when the user asks you to load data they already have (for example weeks 2–13). There are two ways, and the scores are the same either way:

| | One run per file, oldest first | One run for all of them |
|---|---|---|
| Command | `amygda-risk run <folder> --input <file>` per file, in date order (`--no-dashboard` on all but the last) | `amygda-risk run <folder> --input <file1> <file2> ...`, or put them all in `inbox/` and run once |
| Run records | One per file: week-by-week "what changed", warnings and unmatched share | One record for the whole backlog |
| "Since the last run" on the page | Shows the last file's changes | Shows changes across the whole backlog |
| Speed | Slower: one or more score calls per file | Fastest |

Recommend one run per file when the user will look back at how things changed week by week, or wants a warning tied to the file that caused it. Otherwise one run is fine. Never mix the order: a file older than the history already kept is skipped (see "Troubleshooting").

## Reading a run

Each run writes `runs/<run_id>/run.json`, failed runs included (with database storage, read the same records with `Monitor("<folder>").runs()`). The fields to look at:

| Field | Meaning |
|---|---|
| `status` | `ok`; `no_new_data` when every row had been seen before; `failed`, with a plain-language `reason` (nothing was changed) |
| `trigger` | `scheduled` (the app's schedule) or `manual` (**Run now**, or a run you started) |
| `started_at`, `finished_at` | When it ran (UTC) |
| `rows_read`, `rows_already_seen`, `rows_new` | Rows in the files, rows dropped as already scored, rows scored |
| `rows_too_old` | Rows older than the kept history, skipped |
| `new_period` | `start` and `end`: the time range of the new logs this run scored. The Runs tab shows it as "Data" |
| `new_assets` | Assets not in any earlier run. The first run lists every asset, even with history seeded: that is expected, and no warning is given for it |
| `unmatched_share` | Share of the **new** logs that matched no subsystem (`unmatched_basis: "new"`). Against an API older than 4.2.0 it counts the history sent with them too (`"window"`), which dilutes a change |
| `periods_upserted`, `provisional_periods` | Periods scored, and how many are still provisional |
| `changes` | A list with one entry per asset (`asset_id`), highest first: `score_before_run` (none on an asset's first run), `score_now`, `change`, `highest_this_run` (and `_at`), `band_before_run`, `band_of_highest`, `periods_scored`, `first_period`, `last_period` |
| `alerts_raised` | Ids of the alerts this run raised (`amygda-risk alerts <folder>`). Absent when it raised none |
| `warnings` | Sentences to pass on to the user |

Report each run as: new logs, assets scored, assets that reached watch or high in the new data (`band_of_highest`), and the warnings. For a failed run, report the `reason` and that the files wait in `inbox/`.

**Unmatched share.** Some logs never match (routine entries, or codes the model doesn't use), so the first run's share is the model's normal level. Later runs warn when it rises 15 points above that, or when 95% or more match nothing. Compare it with the training data's unmapped share for a fixed-log model (`model_checks` in `monitor.json`).

**Provisional periods.** The period holding the newest log is provisional: more logs for it may still arrive, and the next run replaces its score. Only a period with a score can be provisional: if the newest logs all match no subsystem, that period has no score, and a run can end with 0 provisional periods. That's expected. Say so if the user asks why a recent score changed or why nothing is provisional.

## Troubleshooting

| What happens | Cause | What to do |
|---|---|---|
| `Run FAILED: The Amygda API didn't respond in time` | The API was starting up for longer than the wait, or the network is down | The files wait in `inbox/`; the next run retries. If it keeps happening, check the network from that machine |
| `Run FAILED: The API key was refused` | Wrong or missing key | Check the `.env` file beside the monitor folder and the variable name in `monitor.json` (`api_key_env`) |
| `deployment_name_taken` (409) | A deployment with that name exists | Ask for another name, or whether to delete the old one (`client.list_deployments`) |
| `deployment_limit` (429) | The organisation has 10 deployments | List them with `client.list_deployments` and ask which unused one to delete |
| `payload_too_large` (413) | One upload is over 30 MB | The monitor splits by rows; if it still happens, score shorter date ranges |
| "already a monitor" or "exists and is not empty" | The folder is in use | Pick a new folder. To get rid of the old one, use `amygda-risk remove` after asking (`app.md`, "Removing a monitor") |
| "No timestamp … could be read" | The file's date format differs | Ask how dates are written, set `date_format` in `monitor.json`, and run again |
| "rows are older than the history kept here" | A late or re-sent old file | Old periods keep their scores. For a one-off look, `amygda-risk score <folder> --input <file>` |
| "asset(s) not seen before" | New assets | Normal. Their first `lookback` of scores is low while history builds |
| "matched no subsystem, up from …" | Codes or wording the model never saw | Check the export with the user. If the logs really changed, suggest retraining (Steps 1–12) and deploying the new model under a new name |
| "training logs have codes the model maps to no subsystem" (at `init`) | Gaps in the hierarchy | See "Before deploying" |
| "Another run is in progress" | A run holds `monitor.lock` | Wait. A lock from a crashed run clears itself |
| `deployment_not_found` (404) | The deployment was deleted, or unused for 90 days | Re-create the monitor from the complete model zip, with the old monitor's `history/logs.parquet` as `--history` |

## Without deployments

If the user doesn't want the scoring bundle kept on Amygda's servers, or the API is older than 4.1.0 (no `/v1/deployments`), score new data through a session: open a session, `session.import_model("<complete_model.zip>")`, then go straight to Step 11 (`configure_generation`) and Step 12. Steps 9–10 are skipped. Send the history yourself: include `lookback` of earlier logs (2 × the rolling window for `sum` and `flag`) in the generation file, and keep only the periods from the new data onwards. Nothing is kept on the server after Step 12.
