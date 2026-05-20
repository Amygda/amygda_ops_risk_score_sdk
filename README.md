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

**Internal testing:** Two keys are already live in the hosted API — no setup needed:

| Key | Balance | Use for |
|-----|---------|---------|
| `yk-amygda-dev-normal` | $20 | Normal testing — credit checks pass, balance drops with each LLM step |
| `yk-amygda-dev-low` | $4 | Credit error testing — `InsufficientCreditsError` fires immediately |

**Production:** Contact the Amygda team or log in at https://portal.amygda.io (portal coming soon) to get your own key.

## Quick start

```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig

client = OpsRiskClient()   # connects to hosted API automatically
client.wait_until_ready()

session = client.open_session(api_key="your-api-key", config=SessionConfig(name="my-run"))

# Step 1 — labelling
result = session.configure_labelling_pipeline(
    file_path="examples/sample_data/labelling_sample.csv",
    log_column="cleaned_event_details",
    timestamp_column="timestamp",
    is_free_text=False,
)
```

## Example notebooks

The `examples/notebooks/` folder contains three end-to-end notebooks:

| Notebook | What it covers |
|---|---|
| `01_labelling.ipynb` | Upload logs, build hierarchy, classify |
| `02_risk_score.ipynb` | Train thresholds, generate risk scores, visualise |
| `03_rescore.ipynb` | Score new data against a trained model |

Run them against `examples/sample_data/` to get started.

## Pipeline overview

Two sequential pipelines:

**Labelling** (steps 1–8): Upload log data → extract keywords → generate system/subsystem hierarchy → classify every log entry against the hierarchy.

**Risk Score** (steps 9–12): Upload historical logs → train calibration thresholds → upload new logs → generate per-asset, per-period operational risk scores.

## Requirements

- Python 3.10+
- API key (contact Amygda team)

## License

Private — Amygda internal use only.
