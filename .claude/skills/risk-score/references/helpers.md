# Helper Function Reference — Amygda Ops Risk Score SDK

Load this file before calling any helper function. Functions are grouped by the pipeline step after which they become available.

## Table of Contents

- [After Step 3 — Keyword Helpers](#after-step-3-extract_keywords)
- [After Step 5 — Hierarchy Helpers](#after-step-5-update_hierarchy)
- [After Step 7 — Weight Helpers](#after-step-7-update_weights)
- [After Step 8 — Classification Helpers](#after-step-8-run_classification)
- [After Step 10 — Training/Supervised Helpers](#after-step-10-train_risk_model)
- [After Step 12 — Risk Score Analysis Helpers](#after-step-12-generate_risk_scores)
- [Parameter Naming Summary](#parameter-naming-summary)

---

## After Step 3 (extract_keywords): keyword helpers

### helpers.plot_keyword_cloud

**Signature:** `helpers.plot_keyword_cloud(keywords: Union[str, Dict[str, Any], List[str]], title: str = "Extracted Keywords", max_words: int = 100, width: int = 800, height: int = 400, background_color: str = "white", colormap: str = "viridis", figsize: tuple = (12, 6)) -> None`

**Source accepts:** file path str (to `extract_keywords.json`) | result dict (from `session.extract_keywords()`) | `List[str]` of keyword strings

**Returns:** None (renders inline matplotlib plot)

**Description:** Renders a word-cloud from extracted keywords; falls back to a horizontal bar chart if `wordcloud` is not installed.

**Notes:** First parameter is named `keywords`, not `source` or `source_path`.

---

### helpers.plot_keyword_bar

**Signature:** `helpers.plot_keyword_bar(keywords: Union[str, Dict[str, Any], List[str]], top_n: int = 30, title: str = "Top Keywords", figsize: tuple = (10, 8)) -> None`

**Source accepts:** file path str (to `extract_keywords.json`) | result dict | `List[str]`

**Returns:** None (renders inline matplotlib horizontal bar chart)

**Description:** Horizontal bar chart of the first `top_n` keywords (ranked, no frequency axis — rank only).

**Notes:** First parameter is named `keywords`, not `source` or `source_path`.

---

### helpers.get_top_keywords_table

**Signature:** `helpers.get_top_keywords_table(source: Union[str, Dict[str, Any], List[str]], top_n: int = 50) -> pd.DataFrame`

**Source accepts:** result dict (from `session.extract_keywords()`, reads `keyword_pool` field) | file path str (to `extract_keywords.json`) | bare `{keyword: frequency}` dict | `List[str]` (all frequencies = 1)

**Returns:** `pd.DataFrame` with columns `["Keyword", "Frequency"]`, sorted descending by frequency

**Description:** Returns a DataFrame of the top `top_n` keywords sorted by frequency.

---

### helpers.plot_top_keywords

**Signature:** `helpers.plot_top_keywords(source: Union[str, Dict[str, int], List[str]], top_n: int = 50, title: Optional[str] = None, width: int = 900, height: int = 600) -> None`

**Source accepts:** result dict (from `session.extract_keywords()`) | file path str (to `extract_keywords.json`) | bare `{keyword: frequency}` dict | `List[str]`

**Returns:** None (renders Plotly horizontal bar chart)

**Description:** Horizontal bar chart of the top `top_n` keywords by frequency, mirroring the Streamlit Data Labelling page keyword chart.

---

## After Step 5 (update_hierarchy): hierarchy helpers

### helpers.plot_hierarchy

**Signature:** `helpers.plot_hierarchy(result: Union[str, Dict[str, Any]], title: str = "Generated Hierarchy") -> None`

**Source accepts:** file path str (to `generate_hierarchy.json` or `update_hierarchy.json`) | result dict

**Returns:** None (renders Plotly sunburst chart in notebook)

**Description:** Sunburst chart: inner ring = systems, outer ring = subsystems, cell colour = confidence (green/orange/red).

**Notes:** Requires `plotly`. First parameter is named `result`, not `source`.

---

### helpers.make_hierarchy_rows

**Signature:** `helpers.make_hierarchy_rows(result: Dict[str, Any]) -> List[Dict[str, str]]`

**Source accepts:** result dict only (not a file path — pass `_load_result(path)` first if needed)

**Returns:** `List[Dict]` — editable deep-copy of hierarchy rows, each with keys `system`, `system_confidence`, `subsystem`, `subsystem_confidence`

**Description:** Extracts an editable copy of the hierarchy rows ready to pass back to `session.update_hierarchy(rows=...)`.

**Notes:** Only the four allowed keys are kept. Do NOT add extra keys (e.g. `keywords`) — that raises `ValidationError`. First parameter is named `result`, not `source`.

---

### helpers.hierarchy_to_csv

**Signature:** `helpers.hierarchy_to_csv(result: Union[str, Dict[str, Any]], path: str) -> str`

**Source accepts:** file path str (to `generate_hierarchy.json`) | result dict

**Returns:** `str` — absolute path of the written CSV file

**Description:** Exports the hierarchy to a flat CSV for external editing (e.g. in Excel), then reload with `hierarchy_from_csv`.

---

### helpers.hierarchy_from_csv

**Signature:** `helpers.hierarchy_from_csv(path: str) -> List[Dict[str, str]]`

**Source accepts:** CSV file path only

**Returns:** `List[Dict]` — rows validated to contain only the four required keys, ready for `session.update_hierarchy(rows=...)`

**Description:** Loads an edited hierarchy CSV and returns rows ready for `session.update_hierarchy()`.

---

## After Step 7 (update_weights): weight helpers

### helpers.plot_weights

**Signature:** `helpers.plot_weights(result: Union[str, Dict[str, Any]], title: str = "System & Subsystem Weights", figsize: tuple = (13, 5)) -> None`

**Source accepts:** file path str (to `generate_weights.json` or `update_weights.json`) | result dict

**Returns:** None (renders inline matplotlib two-panel bar chart)

**Description:** Two-panel bar chart: left = system-level weights, right = subsystem weights grouped by system.

**Notes:** First parameter is named `result`, not `source`.

---

### helpers.make_weight_update

**Signature:** `helpers.make_weight_update(result: Dict[str, Any]) -> List[Dict[str, Any]]`

**Source accepts:** result dict only (from `generate_weights()` or `update_weights()`)

**Returns:** `List[Dict]` — deep copy of the weights list with keys `system_name`, `weight`, `subsystems`; each subsystem has `subsystem_name` and `weight`

**Description:** Returns an editable deep copy of the weights list ready to pass to `session.update_weights(systems=...)`.

**Notes:** Only change `weight` values — do NOT rename `system_name` or `subsystem_name`. All system weights must sum to 1.0; each system's subsystem weights must also sum to 1.0 (tolerance 0.0001). First parameter is named `result`.

---

### helpers.normalize_weights

**Signature:** `helpers.normalize_weights(systems: List[Dict[str, Any]], original_systems: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]`

**Source accepts:** `List[Dict]` (from `weights_from_csv` or `make_weight_update`)

**Returns:** New `List[Dict]` with all weights normalised to sum to 1.0

**Description:** Rescales weights so all sums equal exactly 1.0; when `original_systems` is supplied uses smart pin-and-redistribute (locks changed values, scales unchanged ones); otherwise falls back to simple proportional scaling.

**Notes:** Does not modify input in-place — returns a deep copy. Raises `ValueError` if locked weights alone exceed 1.0 or if all weights in a group are 0.

---

### helpers.weights_to_csv

**Signature:** `helpers.weights_to_csv(result: Union[str, Dict[str, Any]], path: str) -> str`

**Source accepts:** file path str (to `generate_weights.json` or `update_weights.json`) | result dict

**Returns:** `str` — absolute path of the written CSV file

**Description:** Exports the weights to a flat CSV (`system_name`, `system_weight`, `subsystem_name`, `subsystem_weight`) for external editing; reload with `weights_from_csv`.

---

### helpers.weights_from_csv

**Signature:** `helpers.weights_from_csv(path: str) -> List[Dict[str, Any]]`

**Source accepts:** CSV file path only

**Returns:** `List[Dict]` — systems list compatible with `session.update_weights(systems=...)`

**Description:** Loads an edited weights CSV and returns a systems list ready for `session.update_weights()`.

**Notes:** Raises `ValueError` if required columns are missing or if the same system has inconsistent `system_weight` values across rows.

---

## After Step 8 (run_classification): classification result helpers

Source: `all_predictions_exploded.parquet` (inside the labelling zip, also at `{artifact_dir}/labels/all_predictions_exploded.parquet`).

### helpers.plot_classification_stacked

**Signature:** `helpers.plot_classification_stacked(source: Union[str, pd.DataFrame], title: Optional[str] = None, width: int = 1000, height: int = 550) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly stacked bar chart: x = system, stacked by subsystem, y = log count)

**Description:** Stacked bar chart of log distribution across systems and subsystems, mirroring the Streamlit labelling Classification Results "Stacked View" tab.

---

### helpers.plot_classification_by_system

**Signature:** `helpers.plot_classification_by_system(source: Union[str, pd.DataFrame], title: Optional[str] = None, width: int = 900, height: int = 500) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly bar chart: x = system name, y = log count)

**Description:** Bar chart of log count per system, mirroring the Streamlit "By System" tab.

---

### helpers.plot_classification_by_subsystem

**Signature:** `helpers.plot_classification_by_subsystem(source: Union[str, pd.DataFrame], top_n: int = 20, title: Optional[str] = None, width: int = 900, height: int = 600) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly horizontal bar chart of top N subsystems by log count)

**Description:** Horizontal bar chart of the top `top_n` subsystems by log count, mirroring the Streamlit "By Subsystem" tab.

---

## After Step 10 (train_risk_model): training validation helpers

### helpers.plot_calibration_thresholds

**Signature:** `helpers.plot_calibration_thresholds(thresholds_source: Union[str, Dict[str, Any]], training_fe_source: Union[str, pd.DataFrame], systems: Optional[List[str]] = None, title: str = "Calibration Threshold Summary", width: int = 1000, height: int = 500) -> None`

**Source accepts:** `thresholds_source`: file path str (to `calibration_thresholds.json`) | dict; `training_fe_source`: file path str (to `training_fe.parquet`) | `pd.DataFrame`

**Returns:** None (renders Plotly overlaid bar chart: max, mean, and threshold per subsystem)

**Description:** Overlaid bar chart showing each subsystem's calibration threshold alongside its mean and max from the training feature data for sanity-checking thresholds.

---

### helpers.plot_training_feature_distributions

**Signature:** `helpers.plot_training_feature_distributions(training_fe_source: Union[str, pd.DataFrame], thresholds_source: Union[str, Dict[str, Any]], systems: Optional[List[str]] = None, max_cols: int = 3, bins: int = 30, width: int = 1100, row_height: int = 280) -> None`

**Source accepts:** `training_fe_source`: file path str (to `training_fe.parquet`) | `pd.DataFrame`; `thresholds_source`: file path str (to `calibration_thresholds.json`) | dict

**Returns:** None (renders Plotly subplot grid of histograms — one per subsystem with threshold vertical line)

**Description:** Grid of histograms showing the distribution of each `_risk_feature` column with the calibration threshold as a vertical red dashed line.

---

### helpers.plot_training_feature_over_time

**Signature:** `helpers.plot_training_feature_over_time(training_fe_source: Union[str, pd.DataFrame], thresholds_source: Union[str, Dict[str, Any]], asset_id: Union[str, List[str]], system: str, subsystem: str, title: Optional[str] = None, width: int = 1000, height: int = 420, resolution: Optional[str] = None) -> None`

**Source accepts:** `training_fe_source`: file path str (to `training_fe.parquet`) | `pd.DataFrame`; `thresholds_source`: file path str (to `calibration_thresholds.json`) | dict

**Returns:** None (renders Plotly time series line chart)

**Description:** Time series of a subsystem's rolling risk feature for one or more assets with the calibration threshold as a horizontal dashed line.

**Notes:** `asset_id` accepts a single string or a list of strings for multi-asset comparison. `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.plot_subsystem_feature_pipeline

**Signature:** `helpers.plot_subsystem_feature_pipeline(training_fe_source: Union[str, pd.DataFrame], thresholds_source: Union[str, Dict[str, Any]], asset_id: str, system: str, subsystem: str, is_free_text: bool = True, logs_mapping: Union[str, Dict[str, List[str]], None] = None, title: Optional[str] = None, width: int = 1000, height: int = 650, resolution: Optional[str] = None) -> None`

**Source accepts:** `training_fe_source`: file path str (to `training_fe.parquet`) | `pd.DataFrame`; `thresholds_source`: file path str (to `calibration_thresholds.json`) | dict

**Returns:** None (renders Plotly 3-panel chart: risk feature + threshold / rolling activity / binary indicators)

**Description:** Three-panel chart showing how the risk feature is built up for a single asset and subsystem: risk feature line with threshold (row 1), raw daily event count or rolling log-code features (row 2), binary event indicator or binary log-code features (row 3).

**Notes:** `is_free_text=False` requires `logs_mapping` (path to `logs_by_system_subsystem.json` or the dict). `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket. For sub-daily data the rolling panel is drawn as stacked areas and the binary/count panels as markers (bars that narrow are invisible over months); daily data keeps bars.

---

### helpers.plot_system_contributions

**Signature:** `helpers.plot_system_contributions(source: Union[str, pd.DataFrame], asset_id: str, model_config: Union[str, Dict[str, Any]], title: Optional[str] = None, width: int = 1000, height: int = 600, resolution: Optional[str] = None) -> None`

**Source accepts:** `source`: file path str (`.parquet` or `.csv`) | `pd.DataFrame`; `model_config`: file path str (to `model_config.json`) | dict

**Returns:** None (renders Plotly stacked bar chart with operational risk line on top)

**Description:** Single-panel stacked bar chart for one asset showing weighted system contributions over time, with the operational risk line tracing the top of the stack. Sub-daily models draw stacked areas instead of bars.

**Notes:** `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.plot_label_timeline

**Signature:** `helpers.plot_label_timeline(feature_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, exclusion_after: Union[int, str] = 7, failure_date_column: str = "failure_date", assets: Optional[List[str]] = None, max_assets: int = 25, title: str = "Failure Label Timeline", width: int = 1100, height: Optional[int] = None) -> None`

**Source accepts:** `feature_source`: file path str (to `training_fe.parquet` or any DataFrame with `asset_id`+`date`) | `pd.DataFrame`; `failures_source`: CSV/parquet file path str | dict | `pd.DataFrame`

**Returns:** None (renders Plotly horizontal scatter timeline coloured by label zone)

**Description:** Horizontal scatter timeline — one row per asset — coloured blue (normal), red (pre-failure), grey (excluded post-failure), with stars for failure events.

**Notes:** `prediction_horizon` / `exclusion_after` accept durations (`"36h"`) or days; pass the same values used in `configure_training` so labels match training. Uses `period_start` (bucket start) when present.

---

### helpers.plot_label_distribution

**Signature:** `helpers.plot_label_distribution(feature_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, exclusion_after: Union[int, str] = 7, failure_date_column: str = "failure_date", freq: str = "W", title: str = "Positive vs Negative Label Distribution Over Time", width: int = 1000, height: int = 400) -> None`

**Source accepts:** `feature_source`: file path str | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** None (renders Plotly stacked bar chart of positive/negative row counts over time)

**Description:** Stacked bar chart of positive and negative row counts over time (excludes excluded rows) to check that positive labels are not all clustered in one narrow time window.

**Notes:** `freq` accepts pandas period strings: `"W"` (weekly), `"M"` (monthly), `"Q"` (quarterly).

---

### helpers.plot_supervised_comparison

**Signature:** `helpers.plot_supervised_comparison(report_source: Union[str, Dict[str, Any]], title: str = "Baseline vs Supervised: Evaluation Metrics", width: int = 680, height: int = 420) -> None`

**Source accepts:** file path str (to `supervised_training_report.json`) | result dict

**Returns:** None (renders Plotly grouped bar chart comparing AUC-ROC and Avg Precision)

**Description:** Grouped bar chart comparing baseline pipeline (unsupervised quantile thresholds + expert weights) against the supervised pipeline (AUC-optimised thresholds + trained weights).

**Notes:** Reads from `supervised_training_report.json` produced by `train_risk_model` when `supervised=True`.

---

### helpers.plot_weight_comparison

**Signature:** `helpers.plot_weight_comparison(expert_source: Union[str, Dict[str, Any]], trained_source: Union[str, Dict[str, Any]], system: Optional[str] = None, title: Optional[str] = None, width: int = 920, height: int = 460) -> None`

**Source accepts:** `expert_source`: file path str (to `model_config.json`) | dict; `trained_source`: file path str (to `trained_weights.json`) | dict

**Returns:** None (renders Plotly grouped bar chart + printed comparison table)

**Description:** Grouped bar chart and printed table comparing expert weights against trained weights at either system level (default) or subsystem level for a given system.

**Notes:** `system=None` shows system-level comparison; `system="motion_control"` (etc.) shows subsystem-level comparison for that system.

---

### helpers.plot_risk_around_failures

**Signature:** `helpers.plot_risk_around_failures(risk_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], failure_date_column: str = "failure_date", prediction_horizon: Union[int, str] = 14, window_after: Union[int, str] = 7, assets: Optional[List[str]] = None, max_assets: int = 6, score_col: str = "operational_risk", title: str = "Risk Score Around Failure Events", width: int = 1100, height: Optional[int] = None) -> None`

**Source accepts:** `risk_source`: file path str (`.parquet` or `.csv`) | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** None (renders Plotly multi-subplot time series — one per failing asset)

**Description:** Time series of operational risk for each failing asset showing the full history, with dashed vertical lines at failure dates and shaded pre-failure horizon regions.

**Notes:** `prediction_horizon` and `window_after` accept durations (`"36h"`) or days.

---

### helpers.plot_failure_risk_stats

**Signature:** `helpers.plot_failure_risk_stats(risk_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, exclusion_after: Union[int, str] = 7, failure_date_column: str = "failure_date", score_col: str = "operational_risk", title: str = "Risk Score Distribution: Pre-failure vs Normal", width: int = 880, height: int = 480) -> None`

**Source accepts:** `risk_source`: file path str | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** None (renders Plotly box plot + printed summary statistics table)

**Description:** Box plot comparing the distribution of `score_col` in the pre-failure window (positive labels) vs normal operation (negative labels), plus a printed statistics table.

---

### helpers.plot_detection_roc

**Signature:** `helpers.plot_detection_roc(risk_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, failure_date_column: str = "failure_date", detection_threshold: Optional[float] = None, score_col: str = "operational_risk", figsize: tuple = (13, 5), title: str = "Optimal detection threshold selection") -> float`

**Source accepts:** `risk_source`: file path str (to a risk scores parquet, e.g. `training_scores.parquet`) | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** `float` — the threshold used (Youden's J optimal if `detection_threshold=None`, otherwise the supplied value)

**Description:** Two-panel matplotlib figure: left = ROC curve with optimal point marked, right = Youden's J vs threshold; prints optimal threshold, AUC-ROC, TPR/FPR.

**Notes:** Requires `scikit-learn`. Returns the threshold so it can be passed directly to `plot_failure_detection_summary`.

---

### helpers.plot_failure_detection_summary

**Signature:** `helpers.plot_failure_detection_summary(risk_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, failure_date_column: str = "failure_date", detection_threshold: Optional[float] = None, score_col: str = "operational_risk", output_csv: Optional[str] = None) -> pd.DataFrame`

**Source accepts:** `risk_source`: file path str | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** `pd.DataFrame` — per-failure table with columns `asset_id`, `failure_date`, `max_risk_in_window`, `caught`, `first_detection_date`, `days_in_advance` (fractional for sub-daily data, e.g. `0.25` = 6h)

**Description:** Builds a per-failure detection audit table (displayed inline), prints a per-asset summary, and optionally saves to CSV; auto-derives Youden's J threshold if `detection_threshold` is not supplied.

**Notes:** Requires `scikit-learn`. Pass the return value as `det_df` to `plot_failure_detection_timeline` to avoid recomputing.

---

### helpers.plot_failure_detection_timeline

**Signature:** `helpers.plot_failure_detection_timeline(risk_source: Union[str, pd.DataFrame], failures_source: Union[str, Dict[str, Any], pd.DataFrame], prediction_horizon: Union[int, str] = 14, failure_date_column: str = "failure_date", detection_threshold: Optional[float] = None, score_col: str = "operational_risk", det_df: Optional[pd.DataFrame] = None, assets: Optional[List[str]] = None, max_assets: int = 25, title: str = "Failure Detection Timeline", width: int = 1100, height: Optional[int] = None) -> None`

**Source accepts:** `risk_source`: file path str | `pd.DataFrame`; `failures_source`: file path str | dict | `pd.DataFrame`

**Returns:** None (renders Plotly horizontal timeline coloured by detection outcome)

**Description:** Horizontal timeline (one row per asset) coloured by detection outcome: green = window caught, orange = window missed, blue = outside window; stars indicate failure events (green = caught, red = missed).

**Notes:** Requires `scikit-learn`. Pass `det_df` from `plot_failure_detection_summary` to skip recomputation of caught/missed status.

---

## After Step 12 (generate_risk_scores): risk score analysis helpers

### helpers.plot_asset_risk_ranking

**Signature:** `helpers.plot_asset_risk_ranking(source: Union[str, pd.DataFrame], asset_id_col: str = "asset_id", score_col: str = "operational_risk", aggregation: str = "mean", top_n: int = 20, title: str = "Asset Risk Scores", figsize: tuple = (12, 6), color_low: str = "#2ecc71", color_high: str = "#e74c3c") -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders inline matplotlib bar chart)

**Description:** Bar chart of per-asset risk scores sorted highest-first, with a green-to-red colour gradient.

**Notes:** `aggregation` must be one of `"mean"`, `"max"`, `"min"`, `"median"`. First parameter is named `source`.

---

### helpers.plot_risk_score_distribution

**Signature:** `helpers.plot_risk_score_distribution(source: Union[str, pd.DataFrame], score_col: str = "operational_risk", bins: int = 30, title: str = "Risk Score Distribution", figsize: tuple = (10, 5)) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders inline matplotlib histogram)

**Description:** Histogram of the risk score distribution across all records in the parquet.

---

### helpers.plot_risk_heatmap

**Signature:** `helpers.plot_risk_heatmap(source: Union[str, pd.DataFrame], metric: str = "operational_risk", asset_ids: Optional[List[str]] = None, title: str = "Multi-Asset Risk Heatmap Over Time", max_heatmap_score: float = 35.0, width: int = 1000, height: int = 500, resolution: Optional[str] = None) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly heatmap: rows = assets, columns = time buckets)

**Description:** Multi-asset risk heatmap over time where each cell is the max risk score for that asset in that time bucket (one column per day for daily models).

**Notes:** `metric` accepts `"operational_risk"` or any `"{system}_system_risk"` column. Use `list_risk_metrics(source)` to discover available columns. `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.plot_daily_risk_snapshot

**Signature:** `helpers.plot_daily_risk_snapshot(source: Union[str, pd.DataFrame], date: str, asset_ids: Optional[List[str]] = None, min_score: float = 0.0, title: str = "Risk Scores by Date", width: int = 1100) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly tile panel — one large operational-risk tile per asset with system-risk sub-tiles)

**Description:** Tile panel for a single date showing colour-coded risk scores (blue 0–33, yellow 33–66, red 66–100) for all assets.

**Notes:** If the exact date is not available the closest date is used automatically. Each tile shows the highest score that day; for sub-daily models `date="YYYY-MM-DD HH:MM"` selects a single bucket.

---

### helpers.plot_asset_risk_over_time

**Signature:** `helpers.plot_asset_risk_over_time(source: Union[str, pd.DataFrame], asset_id: str, model_config: Union[str, Dict[str, Any], None] = None, weighted: bool = False, title: Optional[str] = None, max_heatmap_score: float = 80.0, width: int = 1000, height: int = 400, resolution: Optional[str] = None) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly heatmap: rows = risk types, columns = dates for a single asset)

**Description:** Plotly heatmap for a single asset showing operational risk + each system risk over time.

**Notes:** When `weighted=True`, `model_config` is required (path to `model_config.json` or the dict). First `source` parameter is the risk scores parquet. `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.plot_asset_system_over_time

**Signature:** `helpers.plot_asset_system_over_time(source: Union[str, pd.DataFrame], asset_id: str, system: str, model_config: Union[str, Dict[str, Any], None] = None, weighted: bool = False, title: Optional[str] = None, width: int = 1000, height: int = 400, resolution: Optional[str] = None) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** None (renders Plotly heatmap: rows = system risk + subsystems, columns = dates)

**Description:** Plotly heatmap for a single asset and system showing system-level risk and all its subsystem calibrated risks over time.

**Notes:** `system` must match the system name as it appears in column names (e.g. `"motion_control"`). When `weighted=True`, `model_config` is required. `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.plot_subsystem_log_activity

**Signature:** `helpers.plot_subsystem_log_activity(source: Union[str, pd.DataFrame], asset_id: str, system: str, subsystem: str, date: str, days_back: int = 30, logs_mapping: Union[str, Dict[str, List[str]], None] = None, log_column: Optional[str] = None, risk_source: Union[str, pd.DataFrame, None] = None, is_free_text: bool = True, title: Optional[str] = None, width: int = 1000, height: int = 450, resolution: Optional[str] = None) -> None`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame` — accepts `classified_logs.parquet` (free-text mode) or `risk_scores.parquet` (fixed-log mode)

**Returns:** None (renders Plotly bar chart of log occurrences; with `risk_source` adds rolling/binary feature panels)

**Description:** Bar chart of log occurrences for a specific asset/system/subsystem within a date window; in free-text mode shows daily log counts, in fixed-log mode shows stacked bars per log code.

**Notes:** First parameter is named `source` (NOT `classified_logs_path` or `source_path`). `logs_mapping` is required for fixed-log mode. `is_free_text=False` reads from `risk_scores.parquet` and requires `logs_mapping`. `date="YYYY-MM-DD"` includes that whole day. Bars are per model bucket; `resolution` (e.g. `"12h"`, `"1D"`) combines the model's time buckets into longer periods (highest value per period); `None` (default) plots every bucket.

---

### helpers.get_logs_for_subsystem

**Signature:** `helpers.get_logs_for_subsystem(source: Union[str, pd.DataFrame], asset_id: str, system: str, subsystem: str, date: str, days_back: int = 14, log_column: str = "log_entry") -> pd.DataFrame`

**Source accepts:** file path str (to `classified_logs.parquet`) | `pd.DataFrame`

**Returns:** `pd.DataFrame` — filtered rows with columns `timestamp`, `asset_id`, `system_name`/`system`, `subsystem_name`/`subsystem`, and the log text column; sorted ascending by timestamp

**Description:** Returns raw log entries for a specific asset/system/subsystem within a date window (free-text mode only).

**Notes:** First parameter is named `source` (NOT `classified_logs_path`). Free-text mode only — reads from `classified_logs.parquet`.

---

### helpers.list_risk_metrics

**Signature:** `helpers.list_risk_metrics(source: Union[str, pd.DataFrame]) -> List[str]`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** `List[str]` — always starts with `"operational_risk"` then all `{system}_system_risk` columns sorted alphabetically

**Description:** Returns all valid `metric` values for use with `plot_risk_heatmap`.

---

### helpers.get_risk_breakdown

**Signature:** `helpers.get_risk_breakdown(source: Union[str, pd.DataFrame], asset_id: str, date: str) -> dict`

**Source accepts:** file path str (`.parquet` or `.csv`) | `pd.DataFrame`

**Returns:** `dict` with keys `asset_id`, `date`, `operational_risk`, `systems` (`{system_name: score}`), `subsystems` (`{system-subsystem: score}`)

**Description:** Returns a full risk breakdown for one asset on one date without needing to know system/subsystem names in advance.

**Notes:** If the exact date is not available, the closest date is used and a warning is printed. Scores are the max over the day; for sub-daily models `date="YYYY-MM-DD HH:MM"` returns a single bucket. Raises `ValueError` if the `asset_id` is not found.

---

## Parameter naming summary — common error-prone names

| Function | First source param name | What it accepts |
|---|---|---|
| `plot_keyword_cloud` | `keywords` | dict \| file path \| `List[str]` |
| `plot_keyword_bar` | `keywords` | dict \| file path \| `List[str]` |
| `plot_asset_risk_ranking` | `source` | DataFrame \| file path |
| `plot_risk_score_distribution` | `source` | DataFrame \| file path |
| `plot_hierarchy` | `result` | dict \| file path |
| `make_hierarchy_rows` | `result` | dict only |
| `hierarchy_to_csv` | `result` | dict \| file path |
| `hierarchy_from_csv` | `path` | CSV file path only |
| `plot_weights` | `result` | dict \| file path |
| `plot_risk_heatmap` | `source` | DataFrame \| file path |
| `plot_daily_risk_snapshot` | `source` | DataFrame \| file path |
| `plot_asset_risk_over_time` | `source` | DataFrame \| file path |
| `plot_asset_system_over_time` | `source` | DataFrame \| file path |
| `plot_subsystem_log_activity` | `source` | DataFrame \| file path (NOT `classified_logs_path`) |
| `get_logs_for_subsystem` | `source` | DataFrame \| file path (NOT `classified_logs_path`) |
| `make_weight_update` | `result` | dict only |
| `normalize_weights` | `systems` | `List[Dict]` |
| `weights_to_csv` | `result` | dict \| file path |
| `weights_from_csv` | `path` | CSV file path only |
| `get_top_keywords_table` | `source` | dict \| file path \| freq-dict \| `List[str]` |
| `plot_top_keywords` | `source` | dict \| file path \| freq-dict \| `List[str]` |
| `plot_classification_stacked` | `source` | DataFrame \| file path |
| `plot_classification_by_system` | `source` | DataFrame \| file path |
| `plot_classification_by_subsystem` | `source` | DataFrame \| file path |
| `list_risk_metrics` | `source` | DataFrame \| file path |
| `get_risk_breakdown` | `source` | DataFrame \| file path |
| `plot_calibration_thresholds` | `thresholds_source` | dict \| file path |
| `plot_training_feature_distributions` | `training_fe_source` | DataFrame \| file path |
| `plot_training_feature_over_time` | `training_fe_source` | DataFrame \| file path |
| `plot_subsystem_feature_pipeline` | `training_fe_source` | DataFrame \| file path |
| `plot_system_contributions` | `source` | DataFrame \| file path |
| `plot_label_timeline` | `feature_source` | DataFrame \| file path |
| `plot_label_distribution` | `feature_source` | DataFrame \| file path |
| `plot_supervised_comparison` | `report_source` | dict \| file path |
| `plot_weight_comparison` | `expert_source` | dict \| file path |
| `plot_risk_around_failures` | `risk_source` | DataFrame \| file path |
| `plot_failure_risk_stats` | `risk_source` | DataFrame \| file path |
| `plot_detection_roc` | `risk_source` | DataFrame \| file path |
| `plot_failure_detection_summary` | `risk_source` | DataFrame \| file path |
| `plot_failure_detection_timeline` | `risk_source` | DataFrame \| file path |

**Critical:** `get_logs_for_subsystem` and `plot_subsystem_log_activity` both use `source` as the first parameter name — never `classified_logs_path=` or `source_path=`.
