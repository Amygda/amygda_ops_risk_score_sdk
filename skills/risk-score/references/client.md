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
10. [SessionConfig](#sessionconfig)
11. [Exception hierarchy](#exception-hierarchy)

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
