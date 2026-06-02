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

In the meantime, to request an API key contact the Amygda CEO directly:
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

## Requirements

- Python 3.10+
- API key — contact [faizan@amygdalabs.com](mailto:faizan@amygdalabs.com) to request one (portal coming soon)

