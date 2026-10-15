# Session Method Reference — Amygda Ops Risk Score SDK

## Table of Contents

1. [Session Properties](#session-properties)
2. [Session Utilities](#session-utilities)
3. [Labelling Pipeline (Steps 1–8)](#labelling-pipeline-steps-18)
   - [Step 1 — configure_labelling_pipeline](#step-1--configure_labelling_pipeline)
   - [Step 2 — downsample](#step-2--downsample)
   - [Step 3 — extract_keywords](#step-3--extract_keywords)
   - [Step 4 — generate_hierarchy](#step-4--generate_hierarchy)
   - [Step 5 — update_hierarchy](#step-5--update_hierarchy)
   - [Step 6 — generate_weights](#step-6--generate_weights)
   - [Step 7 — update_weights](#step-7--update_weights)
   - [Step 7b — preview_classification](#step-7b--preview_classification)
   - [Step 8 — run_classification](#step-8--run_classification)
4. [Continuous Scoring](#continuous-scoring)
   - [import_model](#import_model)
5. [Risk Score Pipeline (Steps 9–12)](#risk-score-pipeline-steps-912)
   - [Step 9 — configure_training](#step-9--configure_training)
   - [Step 10 — train_risk_model](#step-10--train_risk_model)
   - [Step 11 — configure_generation](#step-11--configure_generation)
   - [Step 12 — generate_risk_scores](#step-12--generate_risk_scores)

---

## Session Properties

### `auth_id`

```python
@property
def auth_id(self) -> str:
```

Read-only identifier for this session. Pass this value to any API call or artifact lookup that requires `auth_id`.

---

## Session Utilities

### `status()`

```python
def status(self) -> Dict[str, Any]:
```

Returns the current session state and the status of every pipeline step.

**Returns**

| Field | Type | Description |
|-------|------|-------------|
| `auth_id` | str | Session identifier |
| `api_key` | str | Redacted API key associated with this session |
| `name` | str | Human-readable session name |
| `created_at` | str | ISO timestamp of session creation |
| `expires_at` | str | ISO timestamp when the session expires |
| `steps` | dict | Map of step name → step state dict; each step has a `state` field: `NONE`, `RUNNING`, `DONE`, or `FAILED` |
| `config` | dict | Stored pipeline configuration |
| `artifacts` | dict | Stored artifact references |
| `current_error` | str or null | Last error message, if any |

---

### `delete()`

```python
def delete(self) -> Dict[str, Any]:
```

Permanently deletes the server session and all associated stored files. Prefer `OpsRiskClient.restart_session()` to delete and reopen in one call.

**Returns**

| Field | Type | Description |
|-------|------|-------------|
| `message` | str | Confirmation message |
| `auth_id` | str | Session identifier |

---

## Labelling Pipeline (Steps 1–8)

### Step 1 — `configure_labelling_pipeline`

```python
def configure_labelling_pipeline(
    self,
    file_path: str,
    log_column: str,
    asset_column: str,
    max_systems: int,
    max_subsystems: int,
    asset_context: str,
    is_free_text: bool,
    sheet_name: Optional[str] = None,
    *,
    timeout: float = 600.0,
) -> Dict[str, Any]:
```

Uploads the log dataset and locks the labelling pipeline configuration. Must be called before any other labelling step. Re-runnable until Step 2 or Step 3 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Path to the log file (.csv or .xlsx) |
| `log_column` | str | — | Column containing log text or event code |
| `asset_column` | str | — | Column identifying the asset or equipment unit |
| `max_systems` | int | — | Maximum top-level systems for the LLM to generate (1–10) |
| `max_subsystems` | int | — | Maximum subsystems per system (1–5) |
| `asset_context` | str | — | Plain-English description of the asset being analysed |
| `is_free_text` | bool | — | `True` for free-form text logs; `False` for structured codes |
| `sheet_name` | str or None | `None` | XLSX only — sheet to read; `None` auto-detects the first sheet |
| `timeout` | float | `600.0` | Maximum seconds to wait for upload and validation |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `file_path` | str | Always | Absolute path of uploaded file |
| `log_column` | str | Always | Echoed config |
| `asset_column` | str | Always | Echoed config |
| `max_systems` | int | Always | Echoed config |
| `max_subsystems` | int | Always | Echoed config |
| `asset_context` | str | Always | Echoed config |
| `is_free_text` | bool | Always | Echoed config |
| `sheet_name` | str or None | Always | Echoed config |
| `row_count` | int | Always | Number of unique log descriptions in the dataset (not total rows) |
| `downsample_required` | bool | Always | Whether the dataset exceeds the labelling row limit |
| `available_columns` | list | Always | Column names detected in the uploaded file |
| `next_step` | str | Always | Next recommended step |

---

### Step 2 — `downsample`

```python
def downsample(
    self,
    sample_size: int,
    asset_column: Optional[str] = None,
    vehicle_column: Optional[str] = None,
    timestamp_column: Optional[str] = None,
    *,
    file_path: Optional[str] = None,
    sheet_name: Optional[str] = None,
    timeout: float = 600.0,
) -> Dict[str, Any]:
```

Stratified downsample — only callable when `downsample_required == True`. At least one of `asset_column`, `vehicle_column`, `timestamp_column` must be provided. `file_path` and `sheet_name` are keyword-only. Re-runnable until Step 3 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sample_size` | int | — | Target number of rows after downsampling |
| `asset_column` | str or None | `None` | Column identifying the physical asset |
| `vehicle_column` | str or None | `None` | Column identifying the vehicle within an asset |
| `timestamp_column` | str or None | `None` | Column containing the event timestamp |
| `file_path` *(kw-only)* | str or None | `None` | Optional path to the original file for client-side column validation |
| `sheet_name` *(kw-only)* | str or None | `None` | XLSX only |
| `timeout` *(kw-only)* | float | `600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `original_rows` | int | Always | Row count before downsampling |
| `sampled_rows` | int | Always | Row count after downsampling |
| `next_step` | str | Always | Next recommended step |
| `sample_size` | int | Always | Echoed input |
| `asset_column` | str or None | Always | Echoed input |
| `vehicle_column` | str or None | Always | Echoed input |
| `timestamp_column` | str or None | Always | Echoed input |
| `downsampled_path` | str | `artifact_dir` is set | Absolute path to `downsampled.parquet` |

---

### Step 3 — `extract_keywords`

```python
def extract_keywords(
    self,
    extraction_method: str = "fast",
    *,
    linguistic_filter: bool = True,
    timeout: float = 1200.0,
) -> Dict[str, Any]:
```

Scans the uploaded log dataset and extracts a domain vocabulary to feed into `generate_hierarchy`. Re-runnable until Step 4 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `extraction_method` | str | `"fast"` | `"fast"` uses TF-IDF; `"deep"` uses spaCy (slower, better for noisy text) |
| `linguistic_filter` *(kw-only)* | bool | `True` | When `True`, filters out n-grams not recognised as standard English; set `False` to preserve domain jargon |
| `timeout` *(kw-only)* | float | `1200.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `extraction_method` | str | Always | Echoed input |
| `raw_keyword_count` | int | Always | Count at Gate 2, before any post-processing |
| `filtered_keyword_count` | int | Always | Count after substring-duplicate removal |
| `linguistic_filtered_keyword_count` | int | Always | Count of n-grams removed by the linguistic filter; 0 when `linguistic_filter=False` |
| `finalised_keyword_count` | int | Always | Final count sent to the LLM in `generate_hierarchy` |
| `keywords` | list | Always | Finalised keyword list |
| `keyword_pool` | dict | Always | Frequency map of all extracted keywords |
| `next_step` | str | Always | Next recommended step |

---

### Step 4 — `generate_hierarchy`

```python
def generate_hierarchy(
    self,
    *,
    keywords: Optional[List[str]] = None,
    timeout: float = 1200.0,
) -> Dict[str, Any]:
```

Sends the extracted keyword pool to the LLM to build a system/subsystem hierarchy. Blocks for 30 s – 3 min. Re-runnable until Step 5 or Step 6 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keywords` *(kw-only)* | list or None | `None` | Override keyword list; `None` uses the pool from `extract_keywords`. `extract_keywords` must still be completed first. |
| `timeout` *(kw-only)* | float | `1200.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `hierarchy` | list | Always | System/subsystem rows with confidence scores |
| `systems_count` | int | Always | Number of systems generated |
| `subsystems_count` | int | Always | Total subsystems across all systems |
| `keywords_source` | str | Always | `"extract_keywords"` or `"user_override"` |
| `keywords_finalised` | list | Always | Keyword pool actually used after linguistic filtering |
| `keywords_dropped` | list or None | Always | Keywords removed during filtering; `None` when using the extracted pool |

---

### Step 5 — `update_hierarchy`

```python
def update_hierarchy(
    self,
    rows: List[Dict[str, Any]],
    *,
    timeout: float = 1200.0,
) -> Dict[str, Any]:
```

Submits a refined hierarchy, overwriting the previous result. Can be called multiple times. Locked once `generate_weights` is called.

Each dict in `rows` must have keys: `system`, `system_confidence`, `subsystem`, `subsystem_confidence`. Confidence values must be `"high"`, `"medium"`, or `"low"`.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rows` | list[dict] | — | Revised hierarchy rows |
| `timeout` *(kw-only)* | float | `1200.0` | Maximum seconds to wait |

**Returns**

> Note: this return shape is distinct from `generate_hierarchy` — it does not include `keywords_source`, `keywords_finalised`, or `keywords_dropped`.

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `status` | str | Always | Save status from the server |
| `systems_count` | int | Always | Number of systems in the saved hierarchy |
| `subsystems_count` | int | Always | Total subsystems |
| `hierarchy` | list | Always | The saved hierarchy rows |
| `next_step` | str | Always | Next recommended step |
| `rows` | list | Always | Input rows echoed back |

---

### Step 6 — `generate_weights`

```python
def generate_weights(
    self,
    *,
    timeout: float = 300.0,
) -> Dict[str, Any]:
```

Locks the current hierarchy and generates criticality weights. Uses whichever hierarchy is current — `generate_hierarchy` output if `update_hierarchy` was never called, otherwise the latest `update_hierarchy` result. Re-runnable until Step 8 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` *(kw-only)* | float | `300.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `systems_count` | int | Always | Number of systems in the locked hierarchy |
| `next_step` | str | Always | Next recommended step |
| `weights` | list | Always | List of `{system_name, weight, subsystems: [{subsystem_name, weight}]}` |

---

### Step 7 — `update_weights`

```python
def update_weights(
    self,
    systems: List[Dict[str, Any]],
    *,
    original_systems: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 1200.0,
) -> Dict[str, Any]:
```

Overrides system/subsystem criticality weights before classification. Can be called multiple times. Locked once `run_classification` is called. Weights are auto-normalised using pin-and-redistribute logic — pass the result of `generate_weights` or a previous `update_weights` as `original_systems` to enable name-change protection.

Each dict in `systems` must have keys: `system_name`, `weight`, `subsystems` (list of `{subsystem_name, weight}`).

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `systems` | list[dict] | — | Updated system/subsystem weight list |
| `original_systems` *(kw-only)* | list or None | `None` | Unmodified weights from `generate_weights` or a previous `update_weights`; enables name-change protection |
| `timeout` *(kw-only)* | float | `1200.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `systems_count` | int | Always | Number of systems |
| `next_step` | str | Always | Next recommended step |
| `weights` | list | Always | Normalised systems list as saved by the server |

---

### Step 7b — `preview_classification`

```python
def preview_classification(
    self,
    threshold: float = 0.4,
    *,
    timeout: float = 1800.0,
) -> Dict[str, Any]:
```

Previews classification coverage at a given similarity threshold without committing. Repeatable — call with different values to explore the coverage/precision trade-off.

On the first call the server builds the Qdrant vector database and runs a binary search for the optimal threshold. Subsequent calls reuse the cached pool and return instantly.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `threshold` | float | `0.4` | Similarity threshold to evaluate (0.0–1.0) |
| `timeout` *(kw-only)* | float | `1800.0` | Maximum seconds to wait (applies to the first call; subsequent calls are instant) |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `auth_id` | str | Always | Session identifier |
| `optimal_threshold` | float | Always | Server-recommended threshold — highest value that maximises asset coverage |
| `assets_covered` | int | Always | Distinct assets with at least one classified log at `threshold` |
| `total_assets` | int | Always | Total distinct assets in the dataset |
| `logs_classified` | int | Always | Unique log descriptions classified out of total unique descriptions |
| `total_logs` | int | Always | Total unique log descriptions |
| `classified_log_count` | int | Always | Raw-log count classified (pre-dedup; a log appearing 1,000 times counts as 1,000) |
| `total_log_count` | int | Always | Total raw-log count |
| `coverage_by_asset` | list[dict] | Always | Per-asset coverage — see sub-fields below; covered assets first, then uncovered |
| `classification_by_log` | list[dict] | Always | Per unique log description: `log`, `label`, `match_score`, `status`, `log_count`, `asset_ids` |
| `classification_detail` | list[dict] | Always | Flat asset-first view: one dict per `(asset_id, log)` pair, `log_count` is per-asset; equivalent to Streamlit's preview table |

`coverage_by_asset` sub-fields:

| Sub-field | Type | Description |
|-----------|------|-------------|
| `asset_id` | str | Asset identifier |
| `covered` | bool | Whether the asset has at least one classified log |
| `classified_logs` | int | Unique log descriptions classified for this asset |
| `total_logs` | int | Total unique log descriptions for this asset |
| `classified_log_count` | int | Raw classified-log count for this asset |
| `total_log_count` | int | Total raw-log count for this asset |

---

### Step 8 — `run_classification`

> **ONE-WAY DOOR** — cannot be repeated on the same session. The session is automatically wiped after the zip is downloaded.

```python
def run_classification(
    self,
    dest_dir: str,
    similarity_threshold: Optional[float] = None,
    *,
    timeout: float = 3600.0,
) -> Dict[str, Any]:
```

Runs classification and downloads `trained_labelling_model_{auth_id}.zip` to `dest_dir`. Uses the optimal threshold from `preview_classification` if `similarity_threshold` is not supplied; defaults to 0.4 if `preview_classification` was not called.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dest_dir` | str | — | Directory to save the zip into; created if it does not exist |
| `similarity_threshold` | float or None | `None` | Override the similarity threshold (0.0–1.0); `None` uses the server-cached optimal |
| `timeout` *(kw-only)* | float | `3600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `auth_id` | str | Always | Session identifier |
| `zip_path` | str | Always | Absolute local path of the downloaded zip |
| `dest_dir` | str | Always | Absolute path of the destination directory |
| `total_rows` | int | Always | Total log rows classified |
| `similarity_threshold_used` | float | Always | Threshold actually applied |
| `threshold_source` | str | Always | `"user_supplied"`, `"optimal"` (from preview), or `"default"` (0.4 used) |

---

## Continuous Scoring

### `import_model`

```python
def import_model(self, zip_path: str, *, timeout: float = 600.0) -> Dict[str, Any]:
```

Uploads a model zip to this session, skipping the labelling pipeline. Two zip types are accepted:

- **Labelling zip** (`trained_labelling_model_{auth_id}.zip` from `run_classification`): unlocks `configure_training` → `train_risk_model` → `configure_generation` → `generate_risk_scores`.
- **Complete model zip** (`complete_model_{auth_id}.zip` from `generate_risk_scores`): includes training thresholds — skips `configure_training` + `train_risk_model` and unlocks `configure_generation` directly.

To retrain from scratch on a previously-trained session, import the labelling zip (not the complete model zip).

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `zip_path` | str | — | Path to the zip produced by `run_classification` or `generate_risk_scores` |
| `timeout` *(kw-only)* | float | `600.0` | Maximum seconds to wait for upload and extraction |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `is_free_text` | bool | Always | Whether this session's logs are free-form text |
| `log_column` | str | Always | Log column restored from the zip |
| `risk_training_restored` | bool | Always | `True` if the zip contained calibration thresholds (complete model zip); allows skipping to `configure_generation` |
| `next_step` | str | Always | Next recommended step |
| `zip_path` | str | Always | Absolute path of the uploaded zip |

---

## Risk Score Pipeline (Steps 9–12)

### Step 9 — `configure_training`

```python
def configure_training(
    self,
    file_path: str,
    asset_id_column: str,
    timestamp_column: str,
    date_format: str = "infer",
    rolling_window: int = 7,
    rolling_feature_type: str = "sum",
    quantile_for_thresholds: float = 0.99,
    sheet_name: Optional[str] = None,
    supervised: bool = False,
    failures_path: Optional[str] = None,
    failure_date_column: str = "machine_initialisation_date",
    failure_date_format: str = "infer",
    prediction_horizon_days: int = 14,
    exclusion_days_after: int = 7,
    target_imbalance_ratio: Optional[float] = 10.0,
    sampling_strategy: str = "block",
    block_size_days: int = 14,
    n_candidates: int = 200,
    fallback_quantile: float = 0.95,
    min_positives: int = 5,
    lr_c: float = 0.5,
    *,
    timeout: float = 600.0,
) -> Dict[str, Any]:
```

Uploads historical log data and sets risk score training parameters. Re-runnable until Step 10 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Historical log file (.csv or .xlsx) |
| `asset_id_column` | str | — | Column uniquely identifying each asset |
| `timestamp_column` | str | — | Column containing the event timestamp |
| `date_format` | str | `"infer"` | `"infer"` auto-detects; pass a strftime string if detection fails |
| `rolling_window` | int | `7` | Days to aggregate events over (1–30) |
| `rolling_feature_type` | str | `"sum"` | `"sum"`, `"flag"`, `"ewm"`, or `"all"`. `"ewm"` and `"all"` are only valid for fixed-log sessions |
| `quantile_for_thresholds` | float | `0.99` | Calibration percentile (0–1); 0.99 means the top 1% of activity triggers elevated risk |
| `sheet_name` | str or None | `None` | XLSX only |
| `supervised` | bool | `False` | Use AUC-ROC optimisation and logistic regression for threshold and weight learning; requires `failures_path` |
| `failures_path` | str or None | `None` | Path to a failures CSV; required when `supervised=True` |
| `failure_date_column` | str | `"machine_initialisation_date"` | Column in the failures CSV holding the failure date |
| `failure_date_format` | str | `"infer"` | Format of the failure date column |
| `prediction_horizon_days` | int | `14` | Days before a failure to label as positive |
| `exclusion_days_after` | int | `7` | Days after a failure to exclude from training (recovery period) |
| `target_imbalance_ratio` | float or None | `10.0` | Max negatives-to-positives ratio after downsampling; `None` keeps all negatives |
| `sampling_strategy` | str | `"block"` | `"block"` preserves temporal structure; `"random"` samples individual rows |
| `block_size_days` | int | `14` | Calendar-day block size for block-based downsampling |
| `n_candidates` | int | `200` | Threshold candidates evaluated per subsystem |
| `fallback_quantile` | float | `0.95` | Quantile used as fallback when a subsystem has too few positives |
| `min_positives` | int | `5` | Minimum positive rows required to attempt AUC training per subsystem |
| `lr_c` | float | `0.5` | Logistic regression regularisation strength C |
| `timeout` *(kw-only)* | float | `600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `row_count` | int | Always | Number of unique log descriptions in the training dataset (not total rows) |
| `asset_count` | int | Always | Number of distinct assets |
| `is_free_text` | bool | Always | Session log type (restored from labelling config) |
| `supervised` | bool | Always | Echoed config |
| `next_step` | str | Always | Next recommended step |
| `file_path` | str | Always | Absolute path of uploaded training file |
| `asset_id_column` | str | Always | Echoed config |
| `timestamp_column` | str | Always | Echoed config |
| `date_format` | str | Always | Echoed config |
| `rolling_window` | int | Always | Echoed config |
| `rolling_feature_type` | str | Always | Echoed config |
| `quantile_for_thresholds` | float | Always | Echoed config |
| `sheet_name` | str or None | Always | Echoed config |
| `failures_path` | str or None | Always | Absolute path of failures file, or `None` |

---

### Step 10 — `train_risk_model`

```python
def train_risk_model(
    self,
    *,
    timeout: float = 3600.0,
) -> Dict[str, Any]:
```

Trains the risk score model — calibrates per-subsystem thresholds from the training dataset uploaded in `configure_training`. Blocks until complete. Re-runnable until Step 11 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` *(kw-only)* | float | `3600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `auth_id` | str | Always | Session identifier |
| `subsystems_calibrated` | int | Always | Number of subsystems with learned thresholds |
| `supervised` | bool | Always | Whether supervised training was used |
| `baseline_auc_roc` | float or None | Always | AUC-ROC of the unsupervised baseline |
| `supervised_auc_roc` | float or None | Always | AUC-ROC of the supervised model; `None` when `supervised=False` |
| `thresholds_path` | str | `artifact_dir` is set | Absolute path to `calibration_thresholds.json` |
| `training_fe_path` | str | `artifact_dir` is set | Absolute path to `training_fe.parquet` |
| `training_scores_path` | str | `artifact_dir` is set | Absolute path to `training_scores.parquet` |
| `logs_mapping_path` | str | `artifact_dir` is set AND fixed-log session (`is_free_text=False`) | Absolute path to `logs_by_system_subsystem.json` |
| `model_config_path` | str | `artifact_dir` is set AND session was started via `import_model` | Absolute path to `model_config.json` |
| `trained_weights_path` | str | `artifact_dir` is set AND `supervised=True` | Absolute path to `trained_weights.json` |
| `supervised_report_path` | str | `artifact_dir` is set AND `supervised=True` | Absolute path to `supervised_training_report.json` |

> **Note:** `run_training()` is a backward-compat alias for `train_risk_model()`.

---

### Step 11 — `configure_generation`

```python
def configure_generation(
    self,
    file_path: str,
    date_format: str = "infer",
    sheet_name: Optional[str] = None,
    weights_source: str = "labelling",
    *,
    timeout: float = 600.0,
) -> Dict[str, Any]:
```

Uploads the logs to score and locks the generation configuration. The file must have the same column structure as the training dataset. Re-runnable until Step 12 starts.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | — | Log file to score (.csv or .xlsx) |
| `date_format` | str | `"infer"` | `"infer"` auto-detects; pass a strftime string if needed |
| `sheet_name` | str or None | `None` | XLSX only |
| `weights_source` | str | `"labelling"` | `"labelling"` uses expert weights from the labelling step; `"supervised"` uses logistic-regression weights (only valid after `configure_training(supervised=True)` + `train_risk_model()`) |
| `timeout` *(kw-only)* | float | `600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `message` | str | Always | Server confirmation |
| `auth_id` | str | Always | Session identifier |
| `row_count` | int | Always | Number of unique log descriptions in the generation dataset (not total rows) |
| `asset_count` | int | Always | Number of distinct assets |
| `weights_source` | str | Always | Echoed config |
| `next_step` | str | Always | Next recommended step |
| `file_path` | str | Always | Absolute path of uploaded file |
| `date_format` | str | Always | Echoed config |
| `sheet_name` | str or None | Always | Echoed config |

---

### Step 12 — `generate_risk_scores`

> **ONE-WAY DOOR** — cannot be repeated on the same session. The session is automatically wiped after the zip is downloaded and artifacts are extracted.

```python
def generate_risk_scores(
    self,
    dest_dir: str,
    *,
    timeout: float = 3600.0,
) -> Dict[str, Any]:
```

Generates risk scores for every asset in the generation dataset. Downloads `complete_model_{auth_id}.zip` to `dest_dir`, extracts key artifacts into `artifact_dir` (if set), then wipes the session.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dest_dir` | str | — | Directory to save the zip into; created if it does not exist |
| `timeout` *(kw-only)* | float | `3600.0` | Maximum seconds to wait |

**Returns**

| Field | Type | Present when | Description |
|-------|------|--------------|-------------|
| `auth_id` | str | Always | Session identifier |
| `zip_path` | str | Always | Absolute local path of `complete_model_{auth_id}.zip` |
| `dest_dir` | str | Always | Absolute path of the destination directory |
| `assets_scored` | int | Always | Number of assets with generated risk scores |
| `date_range` | dict or None | Always | Date range covered by the scored logs |
| `parquet_path` | str | `artifact_dir` is set | Absolute path to `risk_scores.parquet` |
| `logs_mapping_path` | str | `artifact_dir` is set | Absolute path to `logs_by_system_subsystem.json` |
| `thresholds_path` | str | `artifact_dir` is set | Absolute path to `calibration_thresholds.json` |
| `hierarchy_path` | str | `artifact_dir` is set | Absolute path to `accepted_hierarchy.json` |
| `model_config_path` | str | `artifact_dir` is set | Absolute path to `model_config.json` |
| `classified_logs_path` | str | `artifact_dir` is set AND free-text session | Absolute path to `classified_logs.parquet` |

> **Note:** `run_generation()` is a backward-compat alias for `generate_risk_scores()`.
