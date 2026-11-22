# Amygda Operational Risk Score — Python SDK

Python SDK for the Amygda Operational Risk Score API. The SDK exposes two sequential pipelines: a **data labelling** pipeline that builds a log hierarchy and classifies log entries against it, and a **risk score** pipeline that trains calibration thresholds and generates per-asset operational risk scores from historical and new log data.

## Install

```bash
pip install git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
```

To upgrade to the latest version:

```bash
pip install --upgrade git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
```

## Use it with your AI coding agent

The SDK comes with an agent skill that walks you through the whole pipeline in conversation. Your agent asks the right questions up front, runs each SDK call, shows the charts with guidance on reading them, and warns you before any step that can't be undone. It covers all four journeys (fixed-log or free-text, supervised or unsupervised), an optional results dashboard, and deploying a model to keep scoring new data.

The skill follows the open [Agent Skills](https://agentskills.io) format, so it works with any agent that supports skills, including Claude Code, OpenAI Codex, Cursor, GitHub Copilot and Gemini CLI.

**Option 1: ask your agent to set it up.** Paste this into your agent from the folder you'll work in:

> Install the Amygda ops risk score SDK and its agent skill by following the "Installing the agent skill" section of https://github.com/amygda/amygda_ops_risk_score_sdk

**Option 2: do it yourself.** From the folder you'll work in:

```bash
pip install git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
amygda-risk-skill install
```

Then start a new session in your agent and say something like *"I want to generate risk scores for my equipment logs"*.

### Installing the agent skill

These steps are written so an AI agent can follow them as well as a person.

1. Install or upgrade the SDK in the Python environment the user will work in (Python 3.10+):
   ```bash
   pip install --upgrade git+https://github.com/amygda/amygda_ops_risk_score_sdk.git
   ```
2. From the user's project folder, install the skill. Use the `--agent` value for the agent you are:
   ```bash
   amygda-risk-skill install --agent <claude|codex|cursor|copilot|gemini|other>
   ```
   Leave out `--agent` to install for all agents. Add `--global` to install in the user's home folder so every project can use it.
3. Check it worked: `.claude/skills/risk-score/SKILL.md` (Claude Code) or `.agents/skills/risk-score/SKILL.md` (other agents) now exists.
4. Tell the user to start a new session so the agent picks up the skill, then ask about risk scores to begin.

| Agent | `--agent` | Where the skill goes |
|---|---|---|
| Claude Code | `claude` | `.claude/skills/risk-score/` |
| OpenAI Codex, Cursor, GitHub Copilot, Gemini CLI | `codex`, `cursor`, `copilot`, `gemini` | `.agents/skills/risk-score/` (the shared folder these agents read) |
| An agent without skill support | `other` | `.agents/skills/risk-score/`, plus a short pointer to it in `AGENTS.md` |

Gemini CLI may need skills switched on in its settings. Cursor and Copilot also read `.claude/skills/`, so if you use one of those alone, `--agent cursor` or `--agent copilot` avoids a second copy.

**Keeping it up to date.** The skill ships inside the SDK, so its version always matches. After upgrading the SDK, run `amygda-risk-skill install` again. `amygda-risk-skill uninstall` removes it.

**Chat-only tools** that can't read files: paste `skills/risk-score/SKILL.md` from this repo as the system prompt or project instructions, and add the files in `skills/risk-score/references/` if the tool allows more than one:

| File | Covers |
|---|---|
| `session.md` | Session methods for each pipeline step |
| `client.md` | `OpsRiskClient` constructor and methods |
| `helpers.md` | Plotting and analysis helpers, with how to read each one |
| `data-checks.md` | Checks on the user's data before Step 1 |
| `validation.md` | Checks to run at each stage, including alert bands against failures |
| `agent-execution.md` | How an agent runs each step so progress shows and sessions survive |
| `dashboard.md` | The results dashboard offered after Step 12 |
| `deployment.md` | The deployment half of the fleet app: deploying the model, the checks, and reading a run |
| `app.md` | The fleet app: the questions that decide what it shows, its alerts and schedule, and how it is started and kept running |

## Get an API key

The Amygda API portal is coming soon! Once available, you will be able to log in at
[portal.amygda.io](https://portal.amygda.io) → **API Keys → Create Key**, then paste your key into the notebook.

In the meantime, to request an API key contact the Amygda directly:
[faizan@amygdalabs.com](mailto:faizan@amygdalabs.com)

## Quick start

```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig

client = OpsRiskClient()
client.wait_until_ready()

session = client.open_session(
    api_key="your-api-key",
    config=SessionConfig(name="my-run"),
    artifact_dir="artifacts/my_run/labelling/",
)

# Step 1 — labelling
result = session.configure_labelling_pipeline(
    file_path="how_to/examples/sample_data/fixed_log_training.csv",
    log_column="event_code",
    asset_context="airport baggage sortation station",
    is_free_text=False,
)
```

## Notebooks

The `how_to/` folder contains everything you need to get started:

```
how_to/
├── guides/          # Full reference notebooks (detailed explanations)
│   ├── 01_labelling_guide.ipynb
│   ├── 02_risk_score_guide.ipynb
│   ├── 03_deploy_and_monitor_guide.ipynb
│   └── 04_fleet_app_guide.ipynb
├── examples/        # Lean executable notebooks + sample data
│   ├── 01a_labelling_fixed_log.ipynb
│   ├── 01b_labelling_free_text.ipynb
│   ├── 02a_risk_score_fixed_log_supervised.ipynb
│   ├── 02b_risk_score_fixed_log_unsupervised.ipynb
│   ├── 02c_risk_score_free_text_unsupervised.ipynb
│   ├── 02d_risk_score_free_text_supervised.ipynb
│   ├── 03a_deploy_and_monitor_fixed_log.ipynb
│   ├── 03b_deploy_and_monitor_free_text.ipynb
│   ├── 04a_fleet_app_fixed_log.ipynb
│   └── sample_data/     # Two synthetic datasets, weekly batches and ready-made models (see how_to/how_to.md)
└── how_to.md            # Sample data guide
```

**Start here:** Read the relevant guide notebook in `guides/` first, then run the matching example notebook in `examples/` against the sample data. See `how_to/how_to.md` for a full description of the two datasets.

You can start at any stage: if you haven't run the previous one, the notebooks use ready-made models trained on the sample data (`how_to/examples/sample_data/models/`).

## Pipeline overview

Two sequential pipelines:

**Labelling** (steps 1–8): Upload log data → extract keywords → generate system/subsystem hierarchy → classify every log entry against the hierarchy.

**Risk Score** (steps 9–12): Upload historical logs → train calibration thresholds → upload new logs → generate per-asset, per-period operational risk scores.

## Keep scoring new data: the fleet app

Once you're happy with a model, deploy it and keep scoring new logs as they arrive, with no session and no retraining. The `amygda-risk` command sets up a small app on your own machine: a page you design, with buttons to add files, run now and set a schedule, and alerts when something you care about happens.

```bash
# the API key: in the environment, or in a .env file beside the monitor folder
export AMYGDA_API_KEY=your-api-key

amygda-risk panels                                    # what the page can show
amygda-risk design --spec my_app.json --model complete_model_<id>.zip --open
                                                      # see your layout first; nothing is deployed

# once: deploy the model from Step 12 and create the monitor folder
amygda-risk init fleet_monitor --model complete_model_<id>.zip --name fleet-v1 \
    --history training_logs.csv
amygda-risk design fleet_monitor --spec my_app.json   # tabs, panels, colours, logo, alert rules

amygda-risk app fleet_monitor                         # open it at http://127.0.0.1:8050/
amygda-risk service fleet_monitor --name my-fleet --install   # start it whenever you log in
```

Setting up scores nothing. The app opens waiting for data: add files on the page, or drop them in `fleet_monitor/inbox/`, and press **Run now** or leave them for the schedule.

- **You choose what it shows** in one small JSON file: the title, the tabs, the panels on each, the figures at the top, light or dark, a brand colour and a logo. Nothing in it is code.
- **Alerts** are rules checked after every run: an asset reaches watch or high, a score jumps, an asset goes quiet, a run fails, or too many new logs match nothing. You acknowledge them on the page. They are not sent anywhere.
- **The schedule** (every few hours, daily or weekly) is set, paused and resumed on the page. It runs while the app is running; `amygda-risk service` registers the app with your system so it starts when you log in, under a name you choose. There is nothing to add to cron or Task Scheduler.
- **Every run is recorded**: what was read and scored, the dates the data covered, what changed for each asset, and any warnings. A run that fails is recorded with the reason, and its files stay in `inbox/` for the next run. Each run waits for the hosted API if it's starting up.
- **Storage** is ordinary files, or one SQLite file you can query (`amygda-risk init --storage sqlite`, or `amygda-risk storage fleet_monitor --to sqlite` later).
- **To take a monitor away**, `amygda-risk remove fleet_monitor` lists what it would do (stop the app, delete the deployment, delete the folder), and `--yes` does it.
- The app listens on this machine only, has no login, and needs nothing installed beyond the SDK.

Deploying keeps a small scoring bundle on Amygda's servers, never your log rows: see "Deployed models" under Data retention below. From Python, use `client.deploy_model` and `client.score`, or `Monitor` from `amygda_ops_risk_score.monitor`.

With the agent skill installed, ask your agent for a fleet monitoring app: it asks what the app is called, what you need to see, how it should look, what should raise an alert and how often to check, then sets all of this up. `03_deploy_and_monitor_guide.ipynb` shows the monitor's parts by hand, and `04_fleet_app_guide.ipynb` the app.

## Running the API locally

If you prefer to keep all data on your own machine or use your own LLM API key, you can run the API locally with Docker and point the SDK at `http://localhost:8000`. See [`local_setup/README.md`](local_setup/README.md) for the setup guide.

## Requirements

- Python 3.10+
- API key — contact [faizan@amygdalabs.com](mailto:faizan@amygdalabs.com) to request one (portal coming soon)

## Data & Infrastructure

| | Detail |
|---|---|
| **Compute** | Google Cloud Run — europe-west2 (London, UK) |
| **Intermediate storage** | Google Cloud Storage — europe-west2 (London, UK) |
| **Database** | Google Cloud SQL (PostgreSQL) — europe-west2 (London, UK) |
| **ML models** | Amygda's own models, hosted on GCP Cloud Run — europe-west2 |
| **Large Language Model** | OpenAI API — gpt-6.1-sol — processed keywords only (see below) |

### Data retention

Session data (uploaded log files, intermediate artefacts) is stored temporarily
in GCS during an active pipeline run. **All session data is deleted automatically**
when the pipeline completes or after a maximum of 6 hours — whichever comes first.
Amygda retains no access to customer data after deletion.

Permanent audit records (session ID, timestamp, completion status) are kept in
the database with no customer data content.

#### Deployed models

A deployed model (`client.deploy_model` or `amygda-risk init`) lets you score
new data repeatedly without a session. This is the only case where something
is kept after a pipeline run. By deploying, you agree to it being kept as
described here.

- **What is stored:** the model's scoring bundle, built on your machine from
  `complete_model_*.zip`. It holds system and subsystem names, weights,
  calibration thresholds, and log codes (fixed-log) or keywords (free-text).
  It holds **no asset IDs, timestamps or log rows**. Check exactly what will
  be uploaded with `helpers.describe_bundle(helpers.build_scoring_bundle(zip))`.
- **Where, and for how long:** Google Cloud Storage, europe-west2, encrypted
  at rest, until you delete it (`client.delete_deployment`) or it goes unused
  for 90 days.
- **Logs you send for scoring are never stored.** They are read in memory,
  scored, and discarded. Only the asset ID, timestamp and log columns are
  sent; any other columns stay on your machine. Scores are returned to you
  and not kept.
- **Usage records:** each scoring call records counts only (rows, assets,
  periods, size, duration), with no data content.

If you'd rather no model was kept, don't deploy: keep scoring through
sessions (nothing is kept after a run). A self-hosted scorer that runs on your
own network is coming soon. `client.list_deployments` shows what is deployed,
and `client.delete_deployment` removes a deployment and its bundle at once.

### What is sent to OpenAI

The OpenAI API is used **only** during the `generate_hierarchy` and
`update_hierarchy` steps of the labelling pipeline.

What is sent:
- A list of extracted **keywords** (domain terms derived from log text — not
  the original log entries)
- A plain-text **asset description** (e.g. `"rail rolling stock"`) provided
  by the user

What is **never** sent:
- Original log files or any raw customer data
- Asset IDs, timestamps, or any identifiers from the source data

### No training on customer data

No customer data is used to train Amygda's models or OpenAI's models.
Amygda does not share data with third parties beyond the OpenAI API calls
described above.