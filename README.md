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

## AI coding assistant skill

An agent skill is bundled at `.claude/skills/risk-score/`. It walks any user — technical or non-technical — through the full pipeline conversationally: asking the right upfront questions, executing each SDK call, showing visualisations with interpretation guidance, and flagging irreversible steps. Covers all four journeys (fixed/free-text × supervised/unsupervised) and continuous scoring.

Non-Claude Code tools receive context as **static text injection only** — they cannot follow in-context instructions to load additional files. Where a tool supports multiple context files, add `references/session.md`, `references/client.md`, and `references/helpers.md` (from `.claude/skills/risk-score/references/`) alongside `SKILL.md` for full coverage.

| Tool | How to use it |
|---|---|
| **Claude Code** | `cp -r .claude/skills/risk-score/ ~/.claude/skills/risk-score/` — auto-triggers on "ops risk", "amygda", "equipment risk"; invoke directly with `/risk-score` |
| **Cursor** | Create `.cursor/rules/risk-score.mdc` from `SKILL.md`; add the three `references/*.md` files as additional MDC rules in `.cursor/rules/`, each with `alwaysApply: true` frontmatter |
| **GitHub Copilot** | Single file: paste `SKILL.md` into `.github/copilot-instructions.md`. Multi-file (VS Code / JetBrains): add each as a separate `.github/instructions/*.instructions.md` with `applyTo: "**"` frontmatter |
| **Windsurf / Codeium** | Add `SKILL.md` and the three `references/*.md` files as separate Markdown files in `.windsurf/rules/` |
| **OpenAI Codex (ChatGPT)** | Place `SKILL.md` content in `AGENTS.md` at the repo root; append `references/*.md` content as additional named sections in the same file |
| **JetBrains AI Assistant** | Settings → Tools → AI Assistant → Rules: add `SKILL.md` and each `references/*.md` file as separate rules with "Always apply" activation |
| **Amazon Q Developer** | Add `SKILL.md` as `.amazonq/rules/risk-score.md`; add the three `references/*.md` files as additional files in `.amazonq/rules/` |
| **Gemini Code Assist** | VS Code: paste `SKILL.md` into Gemini Code Assist rules (Settings → search "Gemini Code Assist: Rules"). Agent mode: place `SKILL.md` content in `GEMINI.md` at project root |
| **Any other tool** | Paste `SKILL.md` as a system prompt or project-level context file; include `references/*.md` content inline or as additional context files if the tool supports them |

## Notebooks

The `how_to/` folder contains everything you need to get started:

```
how_to/
├── guides/          # Full reference notebooks (detailed explanations)
│   ├── 01_labelling_guide.ipynb
│   └── 02_risk_score_guide.ipynb
├── examples/        # Lean executable notebooks + sample data
│   ├── 01a_labelling_fixed_log.ipynb
│   ├── 01b_labelling_free_text.ipynb
│   ├── 02a_risk_score_fixed_log_supervised.ipynb
│   ├── 02b_risk_score_fixed_log_unsupervised.ipynb
│   ├── 02c_risk_score_free_text_unsupervised.ipynb
│   ├── 02d_risk_score_free_text_supervised.ipynb
│   └── sample_data/     # Two synthetic datasets (see how_to/README.md)
└── how_to.md            # Sample data guide
```

**Start here:** Read the relevant guide notebook in `guides/` first, then run the matching example notebook in `examples/` against the sample data. See `how_to/how_to.md` for a full description of the two datasets.

## Pipeline overview

Two sequential pipelines:

**Labelling** (steps 1–8): Upload log data → extract keywords → generate system/subsystem hierarchy → classify every log entry against the hierarchy.

**Risk Score** (steps 9–12): Upload historical logs → train calibration thresholds → upload new logs → generate per-asset, per-period operational risk scores.

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