# Local API Setup

Run the Ops Risk API on your own machine so all data stays within your infrastructure and you supply your own LLM API key. The SDK connects to `http://localhost:8000` instead of the hosted endpoint — everything else works identically.

---

## When to use this

- Your data cannot leave your network
- You want to use your own OpenAI or Anthropic account
- You want full control over what is stored and where

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Docker | Docker Desktop 24.x or later (macOS, Windows), or Docker Engine 24.x+ (Linux), running |
| Platform | `linux/amd64` (Intel/AMD: most servers, Windows PCs, Intel Macs) or `linux/arm64` (Apple Silicon Macs, ARM servers). Docker pulls the right image automatically |
| Free disk | ~5 GB (API image ≈ 3.6 GB on disk + your data) |
| RAM | 8 GB free minimum; 12 GB recommended |
| Free port | 8000 must be available |
| LLM API key | OpenAI **or** Anthropic — your own account |

Check the required ports are free before starting:

```bash
lsof -i :8000    # API — should print nothing if free
lsof -i :8501    # Streamlit (only if you plan to run it)
```

If a process is listed, stop it or remap the port in `docker-compose.yml` before continuing:

```yaml
ports:
  - "8002:8000"   # host port 8002 maps to container port 8000
```

---

## Setup

**1. Create a working directory and copy the files from this folder into it:**

```bash
mkdir ops-risk-local && cd ops-risk-local
```

Copy `docker-compose.yml` and `.env.template` from this `local_setup/` folder into `ops-risk-local/`.

**2. Create your `.env` from the template:**

```bash
cp .env.template .env
```

Edit `.env` — fill in your LLM provider and key:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...             ← no quotes around the value

# Anthropic alternative:
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-sonnet-4-5
# ANTHROPIC_API_KEY=sk-ant-...
```

Leave `STORAGE_ROOT`, `DATABASE_URL`, and the `/data/...` paths unchanged — they are container-internal paths and must not be edited.

**3. Start the API:**

> **Linux servers only — create the data folders first.** The containers run as user ID 1000. On Linux, Docker creates missing folders owned by root, and the container then can't write to them. Before the first start, run in this folder:
>
> ```bash
> mkdir -p data trained_models && sudo chown 1000:1000 data trained_models
> ```
>
> If you changed `LOCAL_DATA_DIR` or `TRAINED_MODELS_DIR` in `.env`, use those paths instead. Docker Desktop on macOS and Windows handles this automatically.

```bash
docker compose --profile api up -d
```

Docker pulls the image on first run (~3.6 GB). Allow 60–90 s for ML models to load. Watch startup progress:

```bash
docker logs -f ops-risk-api
```

**4. Create an API key (first time only):**

```bash
docker exec ops-risk-api python seed.py
```

Copy the printed key — you pass it to the SDK. This only needs to be done once. The key persists in `./data/db/labelling.db` across restarts.

---

## Use the SDK against your local API

```python
from amygda_ops_risk_score import OpsRiskClient, SessionConfig
import os

client = OpsRiskClient("http://localhost:8000")   # local instead of hosted
client.wait_until_ready()                          # blocks until models loaded (~60–90 s on cold start)

ARTIFACT_DIR = "artifacts/my_run/labelling/"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

session = client.open_session(
    api_key="demo-<your-key-from-seed>",
    config=SessionConfig(name="my-run"),
    artifact_dir=ARTIFACT_DIR,
)
```

> **Why `artifact_dir` matters:** When a pipeline completes, the session and all its data inside `./data` are cleared automatically. `artifact_dir` tells the SDK to save each step's result as a JSON file on your local machine as the pipeline runs — so your results are preserved even after the session is gone. Always set this before starting a pipeline.

If you remapped the port (e.g. `8002:8000`), use that host port:

```python
client = OpsRiskClient("http://localhost:8002")
```

Everything else — `configure_labelling_pipeline`, `extract_keywords`, `generate_hierarchy`, `run_classification`, etc. — works exactly the same as the hosted API.

---

## Also run the Streamlit UI (optional)

The Streamlit app provides an interactive UI for the labelling and risk score pipelines. It is independent of the SDK.

```bash
docker compose --profile streamlit up -d
```

Open `http://localhost:8501`. `TRAINED_MODELS_DIR` in `.env` is where the app stores the models it produces — point it at any folder on your machine.

> **RAM warning:** each service independently loads ~3–4 GB of ML models. Run both only if you have 16 GB+ RAM free.

To stop Streamlit:

```bash
docker compose --profile streamlit down
```

To wipe Streamlit models and start fresh (API unaffected):

```bash
docker compose --profile streamlit down
rm -rf ./trained_models
docker compose --profile streamlit up -d
```

---

## Stop and restart

**Stop (data preserved):**

```bash
docker compose --profile full down
```

Data in `./data` is untouched. Restart with `docker compose --profile api up -d` — no re-seeding needed.

**Wipe API data and start fresh:**

```bash
docker compose --profile full down
rm -rf ./data
docker compose --profile api up -d
# wait 60–90 s, then:
docker exec ops-risk-api python seed.py
```

**Wipe everything (API data + Streamlit models):**

```bash
docker compose --profile full down
rm -rf ./data ./trained_models
docker compose --profile full up -d
# wait 60–90 s, then:
docker exec ops-risk-api python seed.py
```

Re-seeding is only required when `./data` is deleted.

| Action | Re-seed required? |
|--------|-------------------|
| `docker compose down` then `up` | No |
| `docker compose restart` | No |
| `docker compose pull && up` (upgrade) | No |
| `rm -rf ./data` then `up` | **Yes** |

---

## Data layout

```
./data/                          ← API data (controlled by LOCAL_DATA_DIR in .env)
├── db/
│   └── labelling.db             ← API keys, sessions, usage logs
└── storage/
    └── sessions/
        └── ses-<id>/            ← per-session artefacts (auto-cleaned after expiry)

./trained_models/                ← Streamlit models (controlled by TRAINED_MODELS_DIR in .env)
```

> **Data loss warning:** `LOCAL_DATA_DIR` is a bind mount — the host folder IS the data. Deleting `./data` permanently removes the database and all session artefacts. Re-seed before using the API again.

---

## Path constraints — read before changing anything

Every volume mount in `docker-compose.yml` has two sides separated by `:` — the host path on the left, the container path on the right:

```
${LOCAL_DATA_DIR:-./data}                        :  /data
${TRAINED_MODELS_DIR:-./trained_models}          :  /data/trained_models
```

**The container side never changes.** Inside the container, data is always at `/data`. `STORAGE_ROOT` and `DATABASE_URL` reference container paths — they must always start with `/data/` and do not depend on `LOCAL_DATA_DIR` at all.

| Variable | What it controls | Safe to change? |
|----------|-----------------|-----------------|
| `LOCAL_DATA_DIR` | Where the API data folder lives on your machine | Yes — any host path |
| `TRAINED_MODELS_DIR` | Where trained models live on your machine | Yes — any host path |
| `STORAGE_ROOT` | Path inside the container (always `/data/storage`) | **No** |
| `DATABASE_URL` | Path inside the container (always `/data/db/...`) | **No** |

**Data loss warning:** `LOCAL_DATA_DIR` is a bind mount — the host folder IS the data. Deleting it permanently removes the database and all session artefacts. Re-seed the API before using it again.

---

## Upgrading

```bash
docker compose --profile api pull
docker compose --profile api up -d
```

Data persists. No re-seeding needed.

---

## Inspecting the database

The API stores all keys, sessions, and usage logs in a SQLite database at `./data/db/labelling.db` (where `./data` is whatever `LOCAL_DATA_DIR` points to in `.env`).

Open `inspect_db.ipynb` (in this `local_setup/` folder) — it connects directly to the database and lets you query any table interactively.

Tables in the database:

| Table | Contents |
|-------|----------|
| `api_keys` | API keys created by `seed.py` |
| `sessions` | One row per session ever created |
| `labelling_history` | Completed labelling pipeline runs |
| `risk_score_history` | Completed risk score generation runs |
| `llm_usage` | Token usage per LLM call |
| `step_timing` | Duration of each pipeline step |
| `organisations` | Organisation records |

---

## Managing API keys and organisations

`seed.py` creates exactly one organisation (`Demo Org`) and one API key with `max_concurrent_sessions = 3`. To add keys or change limits, connect to the database directly.

### Change the concurrent session limit for an existing key

```sql
UPDATE api_keys
SET max_concurrent_sessions = 5
WHERE api_key = 'demo-<your-key-here>';
```

No restart needed — the API reads the value fresh from the database on every session create call.

### Create a new organisation

```sql
INSERT INTO organisations (org_name, email, credit_balance_usd)
VALUES ('My Org', 'admin@example.com', 999.0);
-- check the id it got:
SELECT id, org_name FROM organisations;
```

### Create a new API key for that organisation

```sql
INSERT INTO api_keys (api_key, org_id, department_name, max_concurrent_sessions)
VALUES (
    'custom-' || lower(hex(randomblob(16))),
    <org_id from above>,
    'default',
    3
);
-- retrieve and copy the generated key:
SELECT api_key FROM api_keys ORDER BY created_at DESC LIMIT 1;
```

The organisation must exist first — `api_keys.org_id` is a foreign key to `organisations.id`.

---

## Logs

```bash
# Live logs
docker logs -f ops-risk-api
docker logs -f ops-risk-streamlit

# Last 100 lines
docker logs --tail 100 ops-risk-api

# Errors only
docker logs ops-risk-api 2>&1 | grep -i error
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Connection refused` on port 8000 | Models still loading | Wait 60–90 s; `wait_until_ready()` handles this automatically |
| `401 invalid_api_key` | Quoted value in `.env` | Remove quotes around the API key value |
| `CompatibilityError` from `wait_until_ready()` | Outdated image | Run `docker compose --profile api pull && docker compose --profile api up -d` |
| Container exits immediately | Bad `.env` | Run `docker logs ops-risk-api` to see the error |
| Port already in use | Another process on 8000 | Run `lsof -i :8000`; kill it or remap port in `docker-compose.yml` |
| Need to re-seed after restart | `./data` was deleted | Always keep `./data` unless doing a full wipe |
| `LLM bucket calls failed` | Wrong model name | Set `LLM_MODEL=gpt-4o` explicitly in `.env` |
| Streamlit logs full of `ModuleNotFoundError: No module named 'torchvision'` | Outdated image | Run `docker compose --profile streamlit pull && docker compose --profile streamlit up -d` |
