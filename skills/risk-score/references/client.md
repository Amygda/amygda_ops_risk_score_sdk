# OpsRiskClient Reference — Amygda Ops Risk Score SDK

## Table of Contents

1. [OpsRiskClient.__init__](#opsriskclient__init__)
2. [client.close](#clientclose)
3. [client.get_user](#clientget_user)
4. [client.health](#clienthealth)
5. [client.ready](#clientready)
6. [client.wait_until_ready](#clientwait_until_ready)
7. [client.open_session](#clientopen_session)
8. [client.get_session](#clientget_session)
9. [client.restart_session](#clientrestart_session)
10. [Deployed models](#deployed-models) — `deploy_model`, `score`, `list_deployments`, `get_deployment`, `delete_deployment`
11. [SessionConfig](#sessionconfig)
12. [Exception hierarchy](#exception-hierarchy)

---

## OpsRiskClient.__init__

```python
def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0)
```

Initialise the synchronous client for the Ops Risk API.

| Parameter  | Type            | Default                  | Description                                                                                                   |
|------------|-----------------|--------------------------|---------------------------------------------------------------------------------------------------------------|
| `base_url` | `Optional[str]` | `None` (hosted API)      | Override the API URL. Pass `'http://localhost:8000'` for local development; `None` uses the default hosted API. |
| `timeout`  | `float`         | `30.0`                   | Default timeout in seconds for infrastructure calls only (health, open_session, status). Pipeline steps use their own per-step timeouts. |

**Usage:**

```python
client = OpsRiskClient()                        # hosted API
client = OpsRiskClient("http://localhost:8000") # local dev
client = OpsRiskClient(timeout=60.0)            # longer infra timeout
```

---

## client.close

```python
def close(self)
```

Close the underlying HTTP connection. Also usable as a context manager (`with OpsRiskClient() as client:`).

---

## client.get_user

```python
def get_user(self, api_key: str) -> Dict[str, Any]
```

Look up a registered user by API key.

| Parameter | Type  | Default | Description                             |
|-----------|-------|---------|-----------------------------------------|
| `api_key` | `str` | —       | Your API key from the Amygda portal.    |

**Returns:**

| Field        | Type  | Description                          |
|--------------|-------|--------------------------------------|
| `api_key`    | `str` | The key that was looked up.          |
| `created_at` | `str` | ISO-8601 timestamp of key creation.  |

**Raises:** `APIError` with `status_code=404` if the key does not exist.

---

## client.health

```python
def health(self) -> Dict[str, Any]
```

Lightweight liveness check — confirms the API process is running; does not validate models or database.

**Returns:**

| Field    | Type  | Description    |
|----------|-------|----------------|
| `status` | `str` | Always `'ok'`. |

> Use `wait_until_ready()` when you need to confirm ML models are loaded.

---

## client.ready

```python
def ready(self) -> Dict[str, Any]
```

Check whether all ML models are loaded and the API is ready to serve requests.

**Returns:**

| Field    | Type  | Description                                 |
|----------|-------|---------------------------------------------|
| `status` | `str` | `'ready'` or `'loading'`.                   |
| *(other)*| any   | Per-check details from the API response.    |

Returns HTTP 503 with `status: 'loading'` while models are initialising (typically 60–120 s on a cold start).

> Prefer `wait_until_ready()` over calling this directly — it handles retries and progress output.

---

## client.wait_until_ready

```python
def wait_until_ready(self, timeout: float = 3600.0, interval: float = 5.0) -> Dict[str, Any]
```

Poll the API until all ML models are loaded or `timeout` is reached. Prints progress dots to stdout.

| Parameter  | Type    | Default  | Description                                          |
|------------|---------|----------|------------------------------------------------------|
| `timeout`  | `float` | `3600.0` | Maximum seconds to wait before raising `TimeoutError`. |
| `interval` | `float` | `5.0`    | Seconds between polls.                               |

**Returns:** The ready-response dict (same shape as `client.ready()`).

**Raises:**
- `TimeoutError` — if the API is still not ready after `timeout` seconds.
- `CompatibilityError` — if the live API version is older than `OpsRiskClient.MIN_API_VERSION`.
- `ConnectionError` — if the API host is unreachable.

> **Critical:** Returns `Dict[str, Any]`, not `None`. On a warm instance it returns immediately.

---

## client.open_session

```python
def open_session(
    self,
    api_key: str,
    config: SessionConfig,
    artifact_dir: Optional[str] = None,
) -> Session
```

Open a new pipeline session and return a `Session` object ready for Step 1.

| Parameter      | Type            | Default | Description                                                                                       |
|----------------|-----------------|---------|---------------------------------------------------------------------------------------------------|
| `api_key`      | `str`           | —       | Your permanent API key from the Amygda portal.                                                    |
| `config`       | `SessionConfig` | —       | Session identity config — must have a non-blank `name`.                                           |
| `artifact_dir` | `Optional[str]` | `None`  | Local directory for per-step JSON artifacts. Created on first write if it does not yet exist.     |

**Returns:** A `Session` instance starting from Step 1.

**Raises:**
- `ValidationError` — if `config.name` is blank.
- `APIError` — if the server rejects the request (e.g. a live session already exists for this user).

> **Critical:** This method does NOT auto-resume existing sessions. Only one active session is allowed per user at a time. If a previous session is still open, calling `open_session` again will raise a server error. Use `restart_session()` to delete the existing session and start a new one atomically.

---

## client.get_session

```python
def get_session(self, auth_id: str, artifact_dir: Optional[str] = None) -> Session
```

Re-attach to an existing session after a kernel restart or notebook reconnect.

| Parameter      | Type            | Default | Description                                                                               |
|----------------|-----------------|---------|-------------------------------------------------------------------------------------------|
| `auth_id`      | `str`           | —       | The session ID returned when `open_session` was called.                                   |
| `artifact_dir` | `Optional[str]` | `None`  | Same path used when opening the session so remaining steps write to the correct directory. |

Makes one status check to confirm the session is still alive, then returns a fully functional `Session` — steps already marked `DONE` do not need to be re-run.

**Returns:** `Session` reconnected to the existing server-side session.

**Raises:** `APIError` with `status_code=404` if the session has expired or does not exist.

> **Note:** The raised exception is `APIError` (check `exc.status_code == 404`). There is no `SessionNotFoundError` class in this SDK.

---

## client.restart_session

```python
def restart_session(
    self,
    session: Session,
    api_key: str,
    config: SessionConfig,
) -> Session
```

Delete the current session and open a fresh one in a single call.

| Parameter | Type            | Default | Description                                              |
|-----------|-----------------|---------|----------------------------------------------------------|
| `session` | `Session`       | —       | The active `Session` object to discard.                  |
| `api_key` | `str`           | —       | Your API key (same one used to open the original session). |
| `config`  | `SessionConfig` | —       | `SessionConfig` for the new session.                     |

**Returns:** A new `Session` starting from Step 1.

Use this when a step is locked (`StepAlreadyDoneError`) and earlier steps need to be re-run, or any time you need to replace an active session.

> **Warning:** Deletes all session data — the database record and all stored files including generated zips. Download any outputs you need (`run_classification()`, `generate_risk_scores()`) **before** calling this. `LabellingHistory` and `RiskScoreHistory` records survive as permanent audit entries.

---

## Deployed models

A deployed model scores new logs without a session (`references/deployment.md`). Usually the `amygda-risk` monitor calls these for you; use them directly for one-off scoring or to manage deployments.

All of these wait for the API and try once more if it was asleep (the hosted API scales to zero and takes 60–120 s to start). A deployment keeps a small scoring bundle on Amygda's servers until it is deleted or unused for 90 days; `client.deployment_storage_policy()` returns the full wording if the user asks.

### client.deploy_model

```python
def deploy_model(self, api_key: str, model: str, name: str, *, timeout: float = 300.0) -> dict
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `api_key` | `str` | — | The user's API key. |
| `model` | `str` | — | `complete_model_<id>.zip` from Step 12, or a bundle from `helpers.build_scoring_bundle`. The bundle is built locally; raw logs, failures and scores in the zip are never uploaded. |
| `name` | `str` | — | Unique within the organisation, e.g. `"conveyors-v1"`. |

`accept_storage` is no longer needed; older code that passes it still works.

**Returns:** `deployment_id`, `name`, `asset_id_column`, `timestamp_column`, `log_column` (the columns new files need), `feature_frequency`, `rolling_window`, `lookback` (history to send before new logs), `created_at`, `storage_accepted_at`.

**Errors:** `ValidationError` (bad file or name); `APIError` with `deployment_name_taken` (409), `deployment_limit` (429, 10 per organisation) or `payload_too_large` (413).

### client.score

```python
def score(self, api_key: str, deployment_id: str, logs, score_from=None, date_format=None, timeout: float = 900.0) -> DeploymentScores
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `logs` | path or `DataFrame` | — | CSV, XLSX or parquet path, or a DataFrame, in the training data's column layout. Only the three model columns are sent; nothing is stored. |
| `score_from` | date-like | `None` | Start of the new data. Send `lookback` of earlier logs in front and set this; periods before the one holding `score_from` are dropped from the result. |
| `date_format` | `str` | the model's | Override the timestamp format. |

**Returns:** `DeploymentScores`, not a table. The scores are in `.scores` (a DataFrame: one row per asset and period, the same columns as `risk_scores.parquet`); `.diagnostics` has `rows_received`, `rows_in`, `rows_matched`, `unmatched_share`, `assets_scored`, `periods_scored`, `period_min`, `period_max`, `bundle_hash`, and from API 4.2.0 `rows_new`, `rows_new_matched` and `unmatched_share_new` (the same counts for the logs from `score_from` on, without the history sent before them).

```python
res = client.score(api_key, dep_id, "new_logs.csv")
scores = res.scores          # the DataFrame
res.diagnostics["unmatched_share"]
```

To check a new deployment against Step 12, use `helpers.check_deployment` rather than comparing by hand.

Limits per call: 30 MB of logs as parquet; 5,000 rows for free-text models. A period the previous call cut short comes back again in full: replace the earlier row.

### client.list_deployments / client.get_deployment / client.delete_deployment

```python
def list_deployments(self, api_key: str) -> list[dict]
def get_deployment(self, api_key: str, deployment_id: str) -> dict
def delete_deployment(self, api_key: str, deployment_id: str) -> dict
```

`list_deployments` and `get_deployment` add `score_calls`, `last_scored_at` and `idle_expiry_days` (90) to the fields above. `delete_deployment` removes the deployment and its stored bundle immediately; ask the user first, and remember any monitor using it stops working.

---

## SessionConfig

```python
@dataclass
class SessionConfig:
    name: str
```

Identity config passed to `OpsRiskClient.open_session()` and `OpsRiskClient.restart_session()`.

| Field  | Type  | Description                                                                           |
|--------|-------|---------------------------------------------------------------------------------------|
| `name` | `str` | Human-readable label for this session (e.g. `"rail-may-2025"`). Required, non-blank. |

The `name` is for your own reference only — it does not affect processing.

---

## Exception hierarchy

```
OpsRiskSDKError
├── APIError
├── StepError
├── ValidationError
└── CompatibilityError
```

### APIError

Raised for any HTTP 4xx / 5xx response from the API.

| Attribute            | Type   | Description                                                                                |
|----------------------|--------|--------------------------------------------------------------------------------------------|
| `status_code`        | `int`  | HTTP status code (e.g. `404`, `422`, `500`).                                               |
| `error_code`         | `str`  | Machine-readable error identifier from the API response body.                              |
| `message`            | `str`  | Human-readable error description.                                                          |
| `body`               | `dict` | Full raw response body dict.                                                               |
| `retryable`          | `bool` | `True` if the API indicates the same request may succeed on retry.                         |
| `retry_same_session` | `bool` | `False` if the session is corrupted and a new one must be opened before retrying.          |

### StepError

Raised when a pipeline step returns a `FAILED` state.

| Attribute | Type  | Description                                         |
|-----------|-------|-----------------------------------------------------|
| `step`    | `str` | Name of the step that failed (e.g. `"generate_hierarchy"`). |

### ValidationError

Raised for client-side validation failures before any HTTP call is made (e.g. blank `SessionConfig.name`).

| Attribute | Type        | Description                                 |
|-----------|-------------|---------------------------------------------|
| `errors`  | `List[str]` | List of human-readable validation messages. |

### CompatibilityError

Raised by `wait_until_ready()` when the live API version is older than `OpsRiskClient.MIN_API_VERSION`. Ask your admin to redeploy the latest API version.
