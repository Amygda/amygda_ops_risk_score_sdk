"""Helper / visualisation utilities for notebook use.

All functions are optional — they require matplotlib (and optionally wordcloud).
Both are commonly pre-installed in Jupyter environments.  Missing libraries
raise a clear ImportError with the install command.
"""

from __future__ import annotations

import copy
import json as _json
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Internal loader
# ---------------------------------------------------------------------------


def _load_result(source: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Accept a file path (JSON artifact) or a dict.  Always returns a dict."""
    if isinstance(source, str):
        with open(source) as fh:
            return _json.load(fh)
    return source


def _load_keywords(source: Union[str, Dict[str, Any], List[str]]) -> List[str]:
    """Accept a JSON artifact path, a result dict, or a bare list of keywords."""
    if isinstance(source, list):
        return source
    if isinstance(source, str):
        with open(source) as fh:
            data = _json.load(fh)
        return data.get("keywords", [])
    return source.get("keywords", [])


# ---------------------------------------------------------------------------
# Keyword helpers  (use after extract_keywords)
# ---------------------------------------------------------------------------


def plot_keyword_cloud(
    keywords: Union[str, Dict[str, Any], List[str]],
    title: str = "Extracted Keywords",
    max_words: int = 100,
    width: int = 800,
    height: int = 400,
    background_color: str = "white",
    colormap: str = "viridis",
    figsize: tuple = (12, 6),
) -> None:
    """
    Plot a word cloud from an ``extract_keywords()`` result.

    Parameters
    ----------
    keywords:
        Any of:

        - Path to the ``extract_keywords.json`` artifact saved by the SDK.
        - The dict returned by ``session.extract_keywords()``.
        - A plain ``List[str]`` of keyword strings (``result["keywords"]``).
    max_words:
        Maximum number of words to display.
    figsize:
        Matplotlib figure size ``(width_inches, height_inches)``.

    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    try:
        from wordcloud import WordCloud

        _use_wordcloud = True
    except ImportError:
        _use_wordcloud = False

    kw_list = _load_keywords(keywords)
    if not kw_list:
        print("No keywords to plot.")
        return

    if _use_wordcloud:
        wc = WordCloud(
            width=width,
            height=height,
            background_color=background_color,
            colormap=colormap,
            max_words=max_words,
        ).generate(" ".join(kw_list))

        fig, ax = plt.subplots(figsize=figsize)
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title(title, fontsize=14, pad=12)
        plt.tight_layout()
        plt.show()
    else:
        # Fallback: horizontal bar chart of top-N keywords
        _plot_keyword_bar(kw_list[:max_words], title=title, figsize=figsize)


def plot_keyword_bar(
    keywords: Union[str, Dict[str, Any], List[str]],
    top_n: int = 30,
    title: str = "Top Keywords",
    figsize: tuple = (10, 8),
) -> None:
    """
    Horizontal bar chart of the first ``top_n`` keywords.

    Parameters
    ----------
    keywords:
        Any of:

        - Path to the ``extract_keywords.json`` artifact saved by the SDK.
        - The dict returned by ``session.extract_keywords()``.
        - A plain ``List[str]`` of keyword strings (``result["keywords"]``).
    """
    _plot_keyword_bar(
        _load_keywords(keywords), top_n=top_n, title=title, figsize=figsize
    )


def _plot_keyword_bar(
    keywords, top_n: int = 30, title: str = "Top Keywords", figsize=(10, 8)
):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    shown = keywords[:top_n]
    indices = range(len(shown))

    fig, ax = plt.subplots(figsize=figsize)
    ax.barh(
        list(indices), [1] * len(shown), align="center", color="steelblue", alpha=0.7
    )
    ax.set_yticks(list(indices))
    ax.set_yticklabels(shown, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Rank")
    ax.set_title(title, fontsize=13)
    ax.get_xaxis().set_visible(False)
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Risk score helpers  (use after run_generation)
# ---------------------------------------------------------------------------


def _load_dataframe(source: Union[str, "pd.DataFrame"]) -> "pd.DataFrame":
    """Load a parquet or CSV path, or pass through an existing DataFrame."""
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    if isinstance(source, str):
        if source.endswith(".parquet"):
            return pd.read_parquet(source)
        return pd.read_csv(source)
    return source.copy()


def plot_risk_scores(
    source: Union[str, "pd.DataFrame"],
    asset_id_col: str = "asset_id",
    score_col: str = "operational_risk",
    aggregation: str = "mean",
    top_n: int = 20,
    title: str = "Asset Risk Scores",
    figsize: tuple = (12, 6),
    color_low: str = "#2ecc71",
    color_high: str = "#e74c3c",
) -> None:
    """
    Bar chart of per-asset risk scores.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet`` (extracted to ``artifact_dir`` by
        ``run_generation``), a CSV file, **or** a pandas DataFrame already loaded.
    asset_id_col:
        Column name for asset identifier (default ``"asset_id"``).
    score_col:
        Column name for the risk score (default ``"operational_risk"``).
    aggregation:
        How to aggregate multiple rows per asset. One of ``"mean"`` (default),
        ``"max"``, ``"min"``, or ``"median"``.
    top_n:
        How many assets to show (sorted by highest risk first).

    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    _valid_aggs = {"mean", "max", "min", "median"}
    if aggregation not in _valid_aggs:
        raise ValueError(
            f"aggregation must be one of {_valid_aggs}, got '{aggregation}'"
        )

    df = _load_dataframe(source)

    if asset_id_col not in df.columns:
        raise ValueError(
            f"Column '{asset_id_col}' not found. "
            f"Available columns: {list(df.columns)}"
        )
    if score_col not in df.columns:
        raise ValueError(
            f"Column '{score_col}' not found. " f"Available columns: {list(df.columns)}"
        )

    agg = (
        df.groupby(asset_id_col)[score_col]
        .agg(aggregation)
        .dropna()
        .sort_values(ascending=False)
        .head(top_n)
    )

    if agg.empty:
        print(f"No non-NaN values in '{score_col}' — nothing to plot.")
        return

    scores = agg.values
    labels = agg.index.astype(str).tolist()
    max_score = float(max(scores))

    # Colour gradient low→high
    norm = (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)
    colors = [
        tuple(
            float(a) * (1 - n) + float(b) * n
            for a, b in zip(
                plt.matplotlib.colors.to_rgb(color_low),
                plt.matplotlib.colors.to_rgb(color_high),
            )
        )
        for n in norm
    ]

    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.bar(
        range(len(labels)), scores, color=colors, edgecolor="white", linewidth=0.5
    )
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel(f"{aggregation.title()} {score_col.replace('_', ' ').title()}")
    ax.set_title(title, fontsize=13)
    ax.set_ylim(0, max_score * 1.15)

    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_score * 0.01,
            f"{score:.1f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    plt.tight_layout()
    plt.show()


def plot_risk_distribution(
    source: Union[str, "pd.DataFrame"],
    score_col: str = "operational_risk",
    bins: int = 30,
    title: str = "Risk Score Distribution",
    figsize: tuple = (10, 5),
) -> None:
    """
    Histogram of the risk score distribution across all records.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet`` (extracted to ``artifact_dir`` by
        ``run_generation``), a CSV file, **or** a DataFrame.
    score_col:
        Column name for the risk score (default ``"operational_risk"``).
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    df = _load_dataframe(source)

    if score_col not in df.columns:
        raise ValueError(
            f"Column '{score_col}' not found. " f"Available columns: {list(df.columns)}"
        )

    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(
        df[score_col].dropna(),
        bins=bins,
        color="steelblue",
        edgecolor="white",
        alpha=0.8,
    )
    ax.set_xlabel(score_col.replace("_", " ").title())
    ax.set_ylabel("Count")
    ax.set_title(title, fontsize=13)
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Hierarchy helpers  (use after generate_hierarchy / update_hierarchy)
# ---------------------------------------------------------------------------

_CONF_COLORS = {"high": "#2ecc71", "medium": "#f39c12", "low": "#e74c3c"}
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2}


def plot_hierarchy(
    result: Union[str, Dict[str, Any]],
    title: str = "Generated Hierarchy",
) -> None:
    """
    Visualise the hierarchy returned by ``generate_hierarchy()`` or ``update_hierarchy()``.

    Draws an interactive sunburst chart: systems as the inner ring, subsystems as
    the outer ring. Cell colour encodes confidence — green (high), orange (medium),
    red (low).

    Parameters
    ----------
    result:
        Path to the ``generate_hierarchy.json`` or ``update_hierarchy.json`` artifact
        **or** the dict returned directly by those session methods.
        Must contain a ``"hierarchy"`` key.

    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly is required: pip install plotly")

    data = _load_result(result)
    rows = data.get("hierarchy", [])
    if not rows:
        print("No hierarchy data to plot.")
        return

    from collections import defaultdict

    groups: Dict[str, list] = defaultdict(list)
    sys_conf: Dict[str, str] = {}
    for row in rows:
        sname = row["system"]
        groups[sname].append(row)
        sys_conf[sname] = str(row.get("system_confidence", "")).strip().lower()

    _CONF_COLORS = {
        "high": "#2ecc71",
        "medium": "#f39c12",
        "low": "#e74c3c",
    }

    ids, labels, parents, colors, hovers = [], [], [], [], []

    # Root node
    ids.append("root")
    labels.append(title)
    parents.append("")
    colors.append("#2c3e50")
    hovers.append("")

    for sname, subs in groups.items():
        sc = sys_conf.get(sname, "low")
        sys_id = f"sys::{sname}"

        ids.append(sys_id)
        labels.append(sname)
        parents.append("root")
        colors.append(_CONF_COLORS.get(sc, "#95a5a6"))
        hovers.append(f"<b>{sname}</b><br>confidence: {sc}<br>subsystems: {len(subs)}")

        for sub_row in subs:
            subname = sub_row["subsystem"]
            ssc = str(sub_row.get("subsystem_confidence", "")).strip().lower()
            sub_id = f"sub::{sname}::{subname}"

            ids.append(sub_id)
            labels.append(subname)
            parents.append(sys_id)
            colors.append(_CONF_COLORS.get(ssc, "#95a5a6"))
            hovers.append(f"<b>{subname}</b><br>system: {sname}<br>confidence: {ssc}")

    fig = go.Figure(
        go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            marker=dict(colors=colors, line=dict(color="white", width=1.5)),
            hovertext=hovers,
            hoverinfo="text",
            branchvalues="total",
            insidetextorientation="radial",
            textfont=dict(size=11, color="white"),
            maxdepth=3,
        )
    )

    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        margin=dict(t=60, l=10, r=10, b=10),
        paper_bgcolor="#f8f9fa",
        width=700,
        height=700,
    )

    fig.show(renderer="notebook")


def make_hierarchy_rows(result: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract an editable copy of the hierarchy rows from a ``generate_hierarchy()``
    or ``update_hierarchy()`` result, ready to pass back to ``session.update_hierarchy()``.

    Returns a list of dicts with keys:
      ``system``, ``system_confidence``, ``subsystem``, ``subsystem_confidence``

    Edit rules
    ----------
    - **ADD**    — append a new dict to the list.
    - **DELETE** — remove the dict from the list entirely.
    - **UPDATE name** — change the ``system`` or ``subsystem`` string value.
    - **UPDATE confidence** — change to ``'high'``, ``'medium'``, or ``'low'``
      (case-insensitive — ``'HIGH'`` is accepted).
    - **FORBIDDEN** — do not add any other key (e.g. ``'keywords'``).
      Keywords were set during ``extract_keywords`` and cannot be changed here;
      passing them raises a ``ValidationError`` before any network call.

    Each call to ``update_hierarchy()`` **replaces** the entire stored hierarchy
    — it is not a patch/merge.  Pass the complete desired state every time.

    Example
    -------
    ::

        result = session.generate_hierarchy()
        rows = helpers.make_hierarchy_rows(result)

        # Delete a row
        rows = [r for r in rows if r["subsystem"] != "Brake Pads"]

        # Add a new row
        rows.append({
            "system": "Electrical",
            "system_confidence": "medium",
            "subsystem": "Wiring Harness",
            "subsystem_confidence": "low",
        })

        # Change a confidence level
        rows[0]["system_confidence"] = "high"

        session.update_hierarchy(rows=rows)
    """
    _allowed = {"system", "system_confidence", "subsystem", "subsystem_confidence"}
    return [
        {k: v for k, v in row.items() if k in _allowed}
        for row in result.get("hierarchy", [])
    ]


def hierarchy_to_csv(
    result: Union[str, Dict[str, Any]],
    path: str,
) -> str:
    """
    Export the hierarchy from ``generate_hierarchy()`` or ``update_hierarchy()``
    to a CSV file for external editing (e.g. in Excel).

    Columns: ``system``, ``system_confidence``, ``subsystem``, ``subsystem_confidence``

    After editing externally, load it back with :func:`hierarchy_from_csv` and
    pass the result to ``session.update_hierarchy()``.

    Parameters
    ----------
    result:
        The dict returned by ``generate_hierarchy()`` / ``update_hierarchy()``,
        or a path to the saved ``generate_hierarchy.json`` artifact.
    path:
        File path to write the CSV (e.g. ``"artifacts/hierarchy_draft.csv"``).

    Returns
    -------
    Absolute path of the written CSV file.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    import os

    data = _load_result(result)
    rows = make_hierarchy_rows(data)
    df = pd.DataFrame(
        rows,
        columns=["system", "system_confidence", "subsystem", "subsystem_confidence"],
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    df.to_csv(path, index=False)
    return os.path.abspath(path)


def hierarchy_from_csv(path: str) -> List[Dict[str, str]]:
    """
    Load an edited hierarchy CSV and return rows ready for ``session.update_hierarchy()``.

    The CSV must have columns:
    ``system``, ``system_confidence``, ``subsystem``, ``subsystem_confidence``

    Parameters
    ----------
    path:
        Path to the CSV file previously exported with :func:`hierarchy_to_csv`.

    Returns
    -------
    List of row dicts validated to contain only the four required keys.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    df = pd.read_csv(path, dtype=str).fillna("")
    required = {"system", "system_confidence", "subsystem", "subsystem_confidence"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing)}. "
            f"Expected: system, system_confidence, subsystem, subsystem_confidence."
        )
    return df[sorted(required)].to_dict(orient="records")


# ---------------------------------------------------------------------------
# Weight helpers  (use after generate_weights / update_weights)
# ---------------------------------------------------------------------------


def plot_weights(
    result: Union[str, Dict[str, Any]],
    title: str = "System & Subsystem Weights",
    figsize: tuple = (13, 5),
) -> None:
    """
    Visualise weights returned by ``generate_weights()`` or ``update_weights()``.

    Draws two panels side-by-side:
    - Left: system-level weights (bar per system).
    - Right: subsystem weights within each system (grouped bars, one group per system).

    Parameters
    ----------
    result:
        Path to the ``generate_weights.json`` or ``update_weights.json`` artifact
        **or** the dict returned directly by those session methods.
        Must contain a ``"weights"`` key.

    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    data = _load_result(result)
    weights = data.get("weights", [])
    if not weights:
        print("No weight data to plot.")
        return

    sys_names = [w["system_name"] for w in weights]
    sys_vals = [float(w["weight"]) for w in weights]

    fig, (ax_sys, ax_sub) = plt.subplots(1, 2, figsize=figsize)
    fig.suptitle(title, fontsize=13)

    # ── Left panel: system weights ──────────────────────────────────────────
    colors = plt.cm.tab10.colors
    bars = ax_sys.bar(
        sys_names, sys_vals, color=colors[: len(sys_names)], edgecolor="white"
    )
    for bar, val in zip(bars, sys_vals):
        ax_sys.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax_sys.set_ylim(0, 1.15)
    ax_sys.set_ylabel("Weight")
    ax_sys.set_title("System Weights", fontsize=11)
    ax_sys.tick_params(axis="x", rotation=90)

    # ── Right panel: subsystem weights per system ───────────────────────────
    all_sub_labels: List[str] = []
    all_sub_vals: List[float] = []
    all_sub_colors: List[Any] = []
    tick_positions: List[float] = []
    tick_labels: List[str] = []

    x = 0.0
    gap = 0.3
    bar_w = 0.6

    for sys_idx, sys_entry in enumerate(weights):
        subs = sys_entry.get("subsystems", [])
        color = colors[sys_idx % len(colors)]
        start = x
        for sub in subs:
            ax_sub.bar(
                x,
                float(sub["weight"]),
                width=bar_w,
                color=color,
                edgecolor="white",
                alpha=0.85,
            )
            ax_sub.text(
                x,
                float(sub["weight"]) + 0.01,
                f"{float(sub['weight']):.2f}",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=90,
            )
            all_sub_labels.append(sub["subsystem_name"])
            x += bar_w + 0.1
        if subs:
            mid = (start + x - bar_w - 0.1) / 2
            tick_positions.append(mid)
            tick_labels.append(sys_entry["system_name"])
            x += gap

    ax_sub.set_ylim(0, 1.2)
    ax_sub.set_xticks([])
    ax_sub.set_ylabel("Weight")
    ax_sub.set_title("Subsystem Weights (grouped by system)", fontsize=11)

    # Secondary x-axis ticks for group labels
    for pos, lbl in zip(tick_positions, tick_labels):
        ax_sub.text(
            pos + bar_w / 2,
            -0.08,
            lbl,
            ha="right",
            va="top",
            fontsize=8,
            style="italic",
            rotation=90,
            transform=ax_sub.transData,
        )

    plt.tight_layout()
    plt.show()


def _risk_color(score: float) -> str:
    """Map a 0–100 risk score to a hex colour (blue → yellow → red)."""
    if score < 33:
        return "#3498db"
    if score < 66:
        return "#f39c12"
    return "#e74c3c"


def plot_risk_heatmap_multi_asset(
    source: Union[str, "pd.DataFrame"],
    metric: str = "operational_risk",
    asset_ids: Optional[List[str]] = None,
    title: str = "Multi-Asset Risk Heatmap Over Time",
    width: int = 1000,
    height: int = 500,
) -> None:
    """
    Plotly heatmap: rows = assets, columns = dates, cell colour = risk score.

    Mirrors the Multi-Asset Risk Heatmap panel on the Streamlit Risk Score page.
    Each cell is the **max** risk score across all records for that asset on that day.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.
    metric:
        Risk score column to plot.  Two valid forms:

        - ``"operational_risk"``  — overall aggregate risk (default)
        - ``"{system}_system_risk"``  — e.g. ``"conveyor_handling_system_risk"``,
          ``"motion_control_system_risk"``.  Use ``list_risk_metrics(source)`` to
          see every available column.

        The colorbar title is derived automatically from the column name.
    asset_ids:
        Optional subset of assets to include.  Defaults to all assets.
    title:
        Chart title.

    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    df = _load_dataframe(source)

    required = {"asset_id", "date", metric}
    missing = required - set(df.columns)
    if missing:
        system_cols = sorted([c for c in df.columns if c.endswith("_system_risk")])
        raise ValueError(
            f"Column '{metric}' not found.\n"
            f"Valid metric values:\n"
            f"  'operational_risk'\n" + "\n".join(f"  '{c}'" for c in system_cols)
        )

    df["date"] = pd.to_datetime(df["date"]).dt.date
    if asset_ids:
        df = df[df["asset_id"].isin(asset_ids)]

    pivot = df.groupby(["asset_id", "date"])[metric].max().unstack("date").sort_index()
    dates = [str(d) for d in pivot.columns]
    assets = list(pivot.index.astype(str))
    z = pivot.values.tolist()

    # Derive a human-readable colorbar title from the column name
    if metric == "operational_risk":
        colorbar_title = "Operational Risk"
    else:
        colorbar_title = (
            metric.replace("_system_risk", "").replace("_", " ").title()
            + " System Risk"
        )

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=dates,
            y=assets,
            colorscale="RdYlBu_r",
            zmin=0,
            zmax=60,
            colorbar=dict(title=colorbar_title),
            hoverongaps=False,
            hovertemplate="Asset: %{y}<br>Date: %{x}<br>Risk: %{z:.1f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title, x=0.5),
        xaxis=dict(title="Date", tickangle=-45),
        yaxis=dict(title="Asset"),
        width=width,
        height=max(height, len(assets) * 25 + 150),
        margin=dict(l=120, r=40, t=60, b=80),
    )
    fig.show(renderer="notebook")


def plot_risk_scores_by_date(
    source: Union[str, "pd.DataFrame"],
    date: str,
    asset_ids: Optional[List[str]] = None,
    min_score: float = 0.0,
    title: str = "Risk Scores by Date",
    width: int = 1100,
) -> None:
    """
    Tile panel for a single date: one large operational-risk tile per asset,
    with a grid of system-risk tiles beneath it.

    Colour coding: 0–33 blue, 33–66 yellow, 66–100 red.

    Mirrors the "Risk Scores by Date" panel on the Streamlit Risk Score page.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.
    date:
        Date string (``"YYYY-MM-DD"``).  Selects the closest available date.
    asset_ids:
        Optional subset of assets to include.  Defaults to all assets.
    min_score:
        Only show assets whose operational_risk is ≥ this threshold.
    title:
        Chart title.

    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    df = _load_dataframe(source)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    target = pd.to_datetime(date).date()

    if target not in df["date"].values:
        available = sorted(df["date"].unique())
        target = min(available, key=lambda d: abs((d - target).days))

    day_df = df[df["date"] == target].copy()
    if asset_ids:
        day_df = day_df[day_df["asset_id"].isin(asset_ids)]

    agg = day_df.groupby("asset_id").max(numeric_only=True).reset_index()
    agg = agg[agg["operational_risk"] >= min_score].sort_values(
        "operational_risk", ascending=False
    )

    if agg.empty:
        print(f"No assets with operational_risk ≥ {min_score} on {target}.")
        return

    system_cols = sorted([c for c in agg.columns if c.endswith("_system_risk")])
    system_names = [
        c.replace("_system_risk", "").replace("_", " ").title() for c in system_cols
    ]
    assets = agg["asset_id"].astype(str).tolist()
    n_assets = len(assets)

    # Build HTML-like annotation figure with rectangles
    cols_per_row = min(4, n_assets)
    rows_needed = (n_assets + cols_per_row - 1) // cols_per_row

    fig = go.Figure()
    row_h = 0.12
    sys_row_h = 0.08
    total_height = rows_needed * (row_h + len(system_cols) * sys_row_h + 0.05)

    for idx, row in enumerate(agg.itertuples(index=False)):
        col_pos = idx % cols_per_row
        row_pos = idx // cols_per_row
        x0 = col_pos / cols_per_row
        y_top = 1 - row_pos * (row_h + len(system_cols) * sys_row_h + 0.05)
        op_score = float(getattr(row, "operational_risk", 0))
        op_color = _risk_color(op_score)

        fig.add_shape(
            type="rect",
            x0=x0 + 0.01,
            x1=x0 + 0.98 / cols_per_row,
            y0=y_top - row_h,
            y1=y_top,
            fillcolor=op_color,
            line=dict(width=0),
            layer="below",
        )
        fig.add_annotation(
            x=x0 + 0.5 / cols_per_row,
            y=y_top - row_h / 2,
            text=f"<b>{getattr(row, 'asset_id')}</b><br>{op_score:.1f}",
            showarrow=False,
            font=dict(color="white", size=13),
        )

        for sys_idx, (sc, sn) in enumerate(zip(system_cols, system_names)):
            sv = float(getattr(row, sc, 0) or 0)
            sy0 = y_top - row_h - (sys_idx + 1) * sys_row_h
            sy1 = y_top - row_h - sys_idx * sys_row_h
            fig.add_shape(
                type="rect",
                x0=x0 + 0.01,
                x1=x0 + 0.98 / cols_per_row,
                y0=sy0,
                y1=sy1,
                fillcolor=_risk_color(sv),
                opacity=0.85,
                line=dict(width=0),
                layer="below",
            )
            fig.add_annotation(
                x=x0 + 0.5 / cols_per_row,
                y=(sy0 + sy1) / 2,
                text=f"{sn}: {sv:.1f}",
                showarrow=False,
                font=dict(color="white", size=10),
            )

    fig.update_layout(
        title=dict(text=f"{title} — {target}", x=0.5),
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[1 - total_height, 1]),
        width=width,
        height=max(400, int(rows_needed * (150 + len(system_cols) * 60))),
        margin=dict(l=20, r=20, t=60, b=20),
        paper_bgcolor="#f8f9fa",
        plot_bgcolor="#f8f9fa",
    )
    fig.show(renderer="notebook")


def plot_risk_heatmap_single_asset(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    model_config: Union[str, Dict[str, Any], None] = None,
    weighted: bool = False,
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 400,
) -> None:
    """
    Plotly heatmap for a single asset: rows = risk types, columns = dates.

    Row order: Operational Risk at the top, then each system risk.
    Mirrors the "Single Asset Risk Analysis" panel on the Streamlit Risk Score page.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.
    asset_id:
        The asset to analyse.
    model_config:
        Path to ``model_config.json`` or the dict itself. Required when
        ``weighted=True``.
    weighted:
        When ``True``, system rows show weighted contributions
        (``{system}_system_risk × weight``) instead of raw system risk scores.
        The weighted values are comparable in scale to ``operational_risk``.
        Requires ``model_config``.
    title:
        Chart title.  Defaults to ``"Risk Analysis — {asset_id}"``.
    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    system_weights: Dict[str, float] = {}
    if weighted:
        if model_config is None:
            print("weighted=True requires model_config. Pass a path to model_config.json or the dict.")
            return
        cfg = _load_result(model_config) if isinstance(model_config, str) else model_config
        system_weights = cfg.get("system_weights", {})
        if not system_weights:
            print("'system_weights' not found in model_config.")
            return

    df = _load_dataframe(source)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    asset_df = df[df["asset_id"].astype(str) == str(asset_id)]
    if asset_df.empty:
        print(f"Asset '{asset_id}' not found. Available: {list(df['asset_id'].unique()[:10])}")
        return

    system_cols = sorted([c for c in df.columns if c.endswith("_system_risk")])
    pivot = asset_df.groupby("date")[["operational_risk"] + system_cols].max()
    dates = [str(d) for d in pivot.index]

    if weighted:
        z_systems = []
        row_labels_systems = []
        for col in system_cols:
            system = col.replace("_system_risk", "")
            w = system_weights.get(system, 1.0)
            z_systems.append((pivot[col].fillna(0) * w).tolist())
            row_labels_systems.append(
                f"{system.replace('_', ' ').title()} (×{w})"
            )
        hover = "Risk Type: %{y}<br>Date: %{x}<br>Weighted Score: %{z:.2f}<extra></extra>"
        colorbar_title = "Weighted Score"
    else:
        z_systems = [pivot[col].tolist() for col in system_cols]
        row_labels_systems = [
            c.replace("_system_risk", "").replace("_", " ").title() for c in system_cols
        ]
        hover = "Risk Type: %{y}<br>Date: %{x}<br>Score: %{z:.1f}<extra></extra>"
        colorbar_title = "Risk Score"

    z          = [pivot["operational_risk"].tolist()] + z_systems
    row_labels = ["Operational Risk"] + row_labels_systems

    fig = go.Figure(go.Heatmap(
        z=z,
        x=dates,
        y=row_labels,
        colorscale="RdYlBu_r",
        zmin=0,
        zmax=60,
        colorbar=dict(title=colorbar_title),
        hoverongaps=False,
        hovertemplate=hover,
    ))
    fig.update_layout(
        title=dict(text=title or f"Risk Analysis — {asset_id}", x=0.5),
        xaxis=dict(title="Date", tickangle=-45),
        yaxis=dict(title=""),
        width=width,
        height=height,
        margin=dict(l=180, r=40, t=60, b=80),
    )
    fig.show(renderer="notebook")


def plot_system_heatmap_single_asset(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    system: str,
    model_config: Union[str, Dict[str, Any], None] = None,
    weighted: bool = False,
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 400,
) -> None:
    """
    Plotly heatmap for a single asset and system: rows = system risk + its subsystems, columns = dates.

    Row order: system risk at the top, then each subsystem risk below.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.
    asset_id:
        The asset to analyse.
    system:
        System name as it appears in the data (e.g. ``"motion_control"``).
    model_config:
        Path to ``model_config.json`` or the dict itself. Required when
        ``weighted=True``.
    weighted:
        When ``True``, subsystem rows show weighted contributions
        (``{system}-{subsystem}_calibrated_risk × subsystem_weight``) instead
        of raw calibrated risk scores. Requires ``model_config``.
    title:
        Chart title. Defaults to ``"{system} — {asset_id}"``.
    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    subsystem_weights: Dict[str, float] = {}
    if weighted:
        if model_config is None:
            print("weighted=True requires model_config. Pass a path to model_config.json or the dict.")
            return
        cfg = _load_result(model_config) if isinstance(model_config, str) else model_config
        subsystem_weights = cfg.get("subsystem_weights", {}).get(system, {})
        if not subsystem_weights:
            print(f"No subsystem_weights found for system '{system}' in model_config.")
            return

    df = _load_dataframe(source)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    asset_df = df[df["asset_id"].astype(str) == str(asset_id)]
    if asset_df.empty:
        print(f"Asset '{asset_id}' not found. Available: {list(df['asset_id'].unique()[:10])}")
        return

    system_col = f"{system}_system_risk"
    if system_col not in asset_df.columns:
        available = sorted({c.replace("_system_risk", "") for c in df.columns if c.endswith("_system_risk")})
        print(f"System '{system}' not found. Available systems: {available}")
        return

    subsystem_cols = sorted([
        c for c in df.columns
        if c.startswith(f"{system}-") and c.endswith("_calibrated_risk")
    ])

    pivot = asset_df.groupby("date")[[system_col] + subsystem_cols].max()
    dates = [str(d) for d in pivot.index]

    if weighted:
        z_subsystems = []
        row_labels_subsystems = []
        for col in subsystem_cols:
            subsystem = col.replace(f"{system}-", "").replace("_calibrated_risk", "")
            w = subsystem_weights.get(subsystem, 1.0)
            z_subsystems.append((pivot[col].fillna(0) * w).tolist())
            row_labels_subsystems.append(
                f"{subsystem.replace('_', ' ').title()} (×{w})"
            )
        hover = "Row: %{y}<br>Date: %{x}<br>Weighted Score: %{z:.2f}<extra></extra>"
        colorbar_title = "Weighted Score"
    else:
        z_subsystems = [pivot[col].tolist() for col in subsystem_cols]
        row_labels_subsystems = [
            c.replace(f"{system}-", "").replace("_calibrated_risk", "").replace("_", " ").title()
            for c in subsystem_cols
        ]
        hover = "Row: %{y}<br>Date: %{x}<br>Score: %{z:.1f}<extra></extra>"
        colorbar_title = "Risk Score"

    z          = [pivot[system_col].tolist()] + z_subsystems
    row_labels = [system.replace("_", " ").title() + " (System Risk)"] + row_labels_subsystems

    fig = go.Figure(go.Heatmap(
        z=z,
        x=dates,
        y=row_labels,
        colorscale="RdYlBu_r",
        zmin=0,
        zmax=60,
        colorbar=dict(title=colorbar_title),
        hoverongaps=False,
        hovertemplate=hover,
    ))
    fig.update_layout(
        title=dict(text=title or f"{system.replace('_', ' ').title()} — {asset_id}", x=0.5),
        xaxis=dict(title="Date", tickangle=-45),
        yaxis=dict(title=""),
        width=width,
        height=height,
        margin=dict(l=180, r=40, t=60, b=80),
    )
    fig.show(renderer="notebook")


def plot_log_occurrences(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    system: str,
    subsystem: str,
    date: str,
    days_back: int = 30,
    logs_mapping: Union[str, Dict[str, List[str]], None] = None,
    log_column: Optional[str] = None,
    risk_source: Union[str, "pd.DataFrame", None] = None,
    is_free_text: bool = True,
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 450,
) -> None:
    """
    Bar chart of log occurrences for a subsystem within a date window.

    **Free-text mode** — pass ``classified_logs.parquet`` as ``source``.
    The chart shows daily count of classified log entries.

    **Fixed-log mode** — pass ``risk_scores.parquet`` as ``source`` and
    ``logs_mapping``. The chart shows stacked bars of individual log-code counts.

    When ``risk_source`` is provided (``risk_scores.parquet``), two extra panels
    are added below the log count panel showing rolling features (row 2) and
    binary features (row 3) for the same date window, plus risk lines overlaid on
    a secondary y-axis on row 1.

    Parameters
    ----------
    source:
        Path to ``classified_logs.parquet`` (free-text) or ``risk_scores.parquet``
        (fixed-log), or a DataFrame already loaded from either.
    asset_id:
        Asset to filter.
    system:
        System name (e.g. ``"motion_control"``).
    subsystem:
        Subsystem name (e.g. ``"datum_control"``).
    date:
        End date for the window (``"YYYY-MM-DD"``).
    days_back:
        Number of days before ``date`` to include (default 30).
    logs_mapping:
        **Fixed-log mode only.** Path to ``logs_by_system_subsystem.json`` or
        the dict itself.
    log_column:
        Free-text mode only — log text column name, used for hover tooltips.
    risk_source:
        Path to ``risk_scores.parquet`` or a DataFrame. When provided, overlays
        risk lines on a secondary y-axis and adds rolling/binary feature panels.
        In fixed-log mode defaults to ``source`` if not explicitly set.
    is_free_text:
        ``True`` for free-text, ``False`` for fixed-log. Used to resolve the
        correct binary/rolling column names in ``risk_source``.
    title:
        Chart title.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    import datetime as _dt

    df       = _load_dataframe(source)
    end_date   = pd.to_datetime(date).date()
    start_date = end_date - _dt.timedelta(days=days_back)

    source_is_free_text = "system_name" in df.columns or "subsystem_name" in df.columns

    _palette = [
        "#3498db", "#2ecc71", "#9b59b6", "#f39c12", "#1abc9c",
        "#e67e22", "#34495e", "#16a085", "#8e44ad", "#d35400",
        "#27ae60", "#2980b9", "#c0392b", "#7f8c8d", "#f1c40f",
        "#6c5ce7", "#00b894", "#fd79a8", "#e17055", "#74b9ff",
    ]

    # ── In fixed-log mode, default risk_source to source ─────────────────────
    if not source_is_free_text and risk_source is None:
        risk_source = df

    has_risk = risk_source is not None

    # ── Build subplot layout ─────────────────────────────────────────────────
    if has_risk:
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            row_heights=[0.45, 0.3, 0.25],
            vertical_spacing=0.07,
            specs=[[{"secondary_y": True}], [{}], [{}]],
            subplot_titles=["Rolling Features", "Binary Features", "Log Occurrences"],
        )
    else:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

    available_codes: List[str] = []

    # ── Row 1: log count bars ────────────────────────────────────────────────
    if source_is_free_text:
        sys_col = "system_name" if "system_name" in df.columns else "system"
        sub_col = "subsystem_name" if "subsystem_name" in df.columns else "subsystem"
        ts_col  = "timestamp" if "timestamp" in df.columns else "date"

        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        df["_date"] = df[ts_col].dt.date

        mask = (
            (df["asset_id"].astype(str) == str(asset_id))
            & (df[sys_col] == system)
            & (df[sub_col] == subsystem)
            & (df["_date"] >= start_date)
            & (df["_date"] <= end_date)
        )
        window_df = df[mask].copy()
        if window_df.empty:
            print(f"No log entries for asset '{asset_id}' / {system} / {subsystem} "
                  f"between {start_date} and {end_date}.")
            return

        daily = window_df.groupby("_date").size().reset_index(name="count")
        daily["_date"] = daily["_date"].astype(str)

        fig.add_trace(go.Bar(
            x=daily["_date"].tolist(), y=daily["count"].tolist(),
            name="Log Count", marker_color="#3498db",
            hovertemplate="%{x}<br>Count: %{y}<extra></extra>",
        ), row=3 if has_risk else 1, col=1, secondary_y=False)

        chart_title = title or f"Log Occurrences — {asset_id} / {system} / {subsystem}"
        bar_label   = "Log Count"
        barmode     = "relative"

    else:
        if logs_mapping is None:
            print("Fixed-log mode requires logs_mapping.")
            return

        if isinstance(logs_mapping, str):
            with open(logs_mapping) as fh:
                mapping: Dict[str, List[str]] = _json.load(fh)
        else:
            mapping = logs_mapping

        pair      = f"{system}-{subsystem}"
        log_codes = mapping.get(pair, [])
        if not log_codes:
            print(f"No log codes found for '{pair}'.\nAvailable: {list(mapping.keys())}")
            return

        if "date" not in df.columns:
            raise ValueError("Source DataFrame has no 'date' column.")
        df["date"] = pd.to_datetime(df["date"]).dt.date

        mask = (
            (df["asset_id"].astype(str) == str(asset_id))
            & (df["date"] >= start_date)
            & (df["date"] <= end_date)
        )
        window_df = df[mask].sort_values("date")
        if window_df.empty:
            print(f"No data for asset '{asset_id}' between {start_date} and {end_date}.")
            return

        available_codes = [lc for lc in log_codes if lc in window_df.columns]
        if not available_codes:
            print(f"No log-code columns found for '{pair}'.")
            return

        dates_str = [str(d) for d in window_df["date"]]
        for i, lc in enumerate(available_codes):
            label = (lc[:50] + "...") if len(lc) > 50 else lc
            fig.add_trace(go.Bar(
                name=label, x=dates_str,
                y=window_df[lc].fillna(0).tolist(),
                marker_color=_palette[i % len(_palette)],
                legendgroup=lc,
                hovertemplate=f"<b>{lc}</b><br>%{{x}}<br>Count: %{{y}}<extra></extra>",
            ), row=3 if has_risk else 1, col=1, secondary_y=False)

        chart_title = title or f"Individual Log Occurrences Over Time ({days_back} days)"
        bar_label   = "Daily Count"
        barmode     = "stack"

    # ── Risk overlay + rolling/binary panels ─────────────────────────────────
    if has_risk:
        risk_df = _load_dataframe(risk_source) if not isinstance(risk_source, type(df)) else risk_source
        if "date" in risk_df.columns:
            risk_df = risk_df.copy()
            risk_df["date"] = pd.to_datetime(risk_df["date"]).dt.date
            risk_mask = (
                (risk_df["asset_id"].astype(str) == str(asset_id))
                & (risk_df["date"] >= start_date)
                & (risk_df["date"] <= end_date)
            )
            risk_window = risk_df[risk_mask].sort_values("date")
            fe_dates    = [str(d) for d in risk_window["date"]]
            pair        = f"{system}-{subsystem}"

            # Risk lines on row 1 secondary y
            subsystem_col = f"{pair}_calibrated_risk"
            system_col    = f"{system}_system_risk"

            # Risk lines on row 1 (rolling panel) secondary y
            if subsystem_col in risk_window.columns:
                sub_daily = risk_window.groupby("date")[subsystem_col].max().reset_index()
                fig.add_trace(go.Scatter(
                    x=[str(d) for d in sub_daily["date"]],
                    y=sub_daily[subsystem_col].tolist(),
                    name=f"{subsystem.replace('_', ' ').title()} Risk",
                    mode="lines+markers",
                    line=dict(color="#e74c3c", width=2),
                    marker=dict(size=4),
                    hovertemplate="%{x}<br>Subsystem Risk: %{y:.1f}<extra></extra>",
                ), row=1, col=1, secondary_y=True)

            if system_col in risk_window.columns:
                sys_daily = risk_window.groupby("date")[system_col].max().reset_index()
                fig.add_trace(go.Scatter(
                    x=[str(d) for d in sys_daily["date"]],
                    y=sys_daily[system_col].tolist(),
                    name=f"{system.replace('_', ' ').title()} Risk",
                    mode="lines+markers",
                    line=dict(color="#f39c12", width=2, dash="dash"),
                    marker=dict(size=4),
                    hovertemplate="%{x}<br>System Risk: %{y:.1f}<extra></extra>",
                ), row=1, col=1, secondary_y=True)

            # Row 1: rolling, Row 2: binary
            if is_free_text:
                roll_col = next(
                    (c for c in risk_df.columns
                     if c.endswith(f"_binary_{pair}") and c.startswith("rolling_")),
                    None,
                )
                if roll_col and roll_col in risk_window.columns:
                    fig.add_trace(go.Bar(
                        x=fe_dates, y=risk_window[roll_col].fillna(0).tolist(),
                        name="Rolling Feature", showlegend=False,
                        marker_color="#7fb3d3",
                        hovertemplate="%{x}<br>Rolling: %{y:.2f}<extra></extra>",
                    ), row=1, col=1)

                bin_col = f"binary_{pair}"
                if bin_col in risk_window.columns:
                    fig.add_trace(go.Bar(
                        x=fe_dates, y=risk_window[bin_col].fillna(0).tolist(),
                        name="Binary", showlegend=False,
                        marker_color="#e67e22",
                        hovertemplate="%{x}<br>Binary: %{y}<extra></extra>",
                    ), row=2, col=1)

            else:
                rolling_prefix = None
                for lc in available_codes:
                    cands = [
                        c for c in risk_df.columns
                        if c.endswith(f"_binary_{lc}") and c.startswith("rolling_")
                    ]
                    if cands:
                        rolling_prefix = cands[0][: -len(f"_binary_{lc}")]
                        break

                for i, lc in enumerate(available_codes):
                    color = _palette[i % len(_palette)]
                    label = (lc[:40] + "...") if len(lc) > 40 else lc

                    if rolling_prefix:
                        roll_col = f"{rolling_prefix}_binary_{lc}"
                        if roll_col in risk_window.columns:
                            fig.add_trace(go.Bar(
                                x=fe_dates,
                                y=risk_window[roll_col].fillna(0).tolist(),
                                name=label, marker_color=color,
                                legendgroup=lc, showlegend=False,
                                hovertemplate=f"<b>{lc}</b><br>%{{x}}<br>Rolling: %{{y:.2f}}<extra></extra>",
                            ), row=1, col=1)

                    bin_col = f"binary_{lc}"
                    if bin_col in risk_window.columns:
                        fig.add_trace(go.Bar(
                            x=fe_dates,
                            y=risk_window[bin_col].fillna(0).tolist(),
                            name=label, marker_color=color,
                            legendgroup=lc, showlegend=False,
                            hovertemplate=f"<b>{lc}</b><br>%{{x}}<br>Binary: %{{y}}<extra></extra>",
                        ), row=2, col=1)

    layout = dict(
        barmode=barmode,
        title=dict(text=chart_title, x=0.5),
        yaxis=dict(title=bar_label),
        yaxis2=dict(title="Risk Score (0–100)", range=[0, 100]),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        width=width,
        height=height if not has_risk else height + 300,
        margin=dict(l=60, r=200, t=60, b=80),
    )
    if has_risk:
        layout["xaxis3"] = dict(title="Date", tickangle=-45)
        layout["yaxis"]  = dict(title="Rolling Value")
        layout["yaxis2"] = dict(title="Risk Score (0–100)", range=[0, 100])
        layout["yaxis3"] = dict(title="Binary (0/1)")
        layout["yaxis4"] = dict(title=bar_label)
        layout["barmode"] = "stack"
    else:
        layout["xaxis"] = dict(title="Date", tickangle=-45)

    fig.update_layout(**layout)
    fig.show(renderer="notebook")


def get_logs_for_subsystem(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    system: str,
    subsystem: str,
    date: str,
    days_back: int = 14,
    log_column: str = "log_entry",
) -> "pd.DataFrame":
    """
    Return a DataFrame of raw log entries for a specific asset / system / subsystem
    within a date window.

    **Free-text mode only** — reads from ``classified_logs.parquet``, which is
    extracted to ``artifact_dir`` by ``run_generation()`` when ``is_free_text=True``.

    Mirrors the raw log table on the Streamlit Risk Score page.

    Parameters
    ----------
    source:
        Path to ``classified_logs.parquet`` (in ``artifact_dir``), or a DataFrame
        already loaded from it.
    asset_id:
        Asset to filter.
    system:
        System name to filter.
    subsystem:
        Subsystem name to filter.
    date:
        End date for the window (``"YYYY-MM-DD"``).
    days_back:
        Number of days before ``date`` to include (default 14).
    log_column:
        Name of the raw log text column (default ``"log_entry"``).

    Returns
    -------
    Filtered DataFrame with columns: ``timestamp``, ``asset_id``,
    ``system_name``, ``subsystem_name``, and ``log_column``.
    Sorted by timestamp ascending.

    Example
    -------
    ::

        classified_logs_path = generation_result.get("classified_logs_path") or \\
                               f"{ARTIFACT_DIR}classified_logs.parquet"
        logs_df = helpers.get_logs_for_subsystem(
            classified_logs_path,
            asset_id="12345",
            system="Brakes",
            subsystem="Pads",
            date="2024-03-15",
        )
        display(logs_df)
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    df = _load_dataframe(source)

    end_date = pd.to_datetime(date)
    start_date = end_date - __import__("datetime").timedelta(days=days_back)

    sys_col = (
        "system_name"
        if "system_name" in df.columns
        else ("system" if "system" in df.columns else None)
    )
    sub_col = (
        "subsystem_name"
        if "subsystem_name" in df.columns
        else ("subsystem" if "subsystem" in df.columns else None)
    )

    base_mask = df["asset_id"].astype(str) == str(asset_id)
    if sys_col:
        base_mask = base_mask & (df[sys_col] == system)
    if sub_col:
        base_mask = base_mask & (df[sub_col] == subsystem)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        mask = (
            base_mask & (df["timestamp"] >= start_date) & (df["timestamp"] <= end_date)
        )
    else:
        mask = base_mask

    keep_cols = [c for c in ["timestamp", "asset_id"] if c in df.columns]
    if sys_col:
        keep_cols.append(sys_col)
    if sub_col:
        keep_cols.append(sub_col)
    if log_column in df.columns:
        keep_cols.append(log_column)

    sort_col = "timestamp" if "timestamp" in df.columns else keep_cols[0]
    result = df[mask][keep_cols].sort_values(sort_col).reset_index(drop=True)
    return result


def make_weight_update(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return an editable deep copy of the weights list from ``generate_weights()``
    or ``update_weights()``, ready to pass to ``session.update_weights()``.

    Edit rules
    ----------
    - **ONLY** change the numeric ``weight`` values (int or float).
    - **NEVER** change ``system_name`` or ``subsystem_name`` — doing so raises
      ``ValidationError`` when you pass ``original_systems`` to ``update_weights()``.
    - All system weights must sum to 1.0.
    - Each system's subsystem weights must also sum to 1.0.
    - A tolerance of 0.0001 is applied, so ``0.33 + 0.33 + 0.34`` is accepted.

    Example
    -------
    ::

        result = session.generate_weights()
        helpers.plot_weights(result)          # visualise before editing

        weights = helpers.make_weight_update(result)

        # Edit weight values only — do NOT rename systems or subsystems
        weights[0]["weight"] = 0.7
        weights[1]["weight"] = 0.3
        weights[0]["subsystems"][0]["weight"] = 0.6
        weights[0]["subsystems"][1]["weight"] = 0.4

        # Pass original_systems to lock names client-side before the HTTP call
        session.update_weights(systems=weights, original_systems=result["weights"])

    Returns
    -------
    List of weight dicts (deep copy — editing does not affect the original result).
    """
    _sys_allowed = {"system_name", "weight", "subsystems"}
    _sub_allowed = {"subsystem_name", "weight"}
    return [
        {
            k: (
                round(v, 4)
                if k == "weight"
                else (
                    [
                        {
                            "subsystem_name": sub["subsystem_name"],
                            "weight": round(sub["weight"], 4),
                        }
                        for sub in v
                        if "subsystem_name" in sub
                    ]
                    if k == "subsystems"
                    else v
                )
            )
            for k, v in sys_entry.items()
            if k in _sys_allowed
        }
        for sys_entry in result.get("weights", [])
    ]


def normalize_weights(
    systems: List[Dict[str, Any]],
    original_systems: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Rescale weights so that all sums equal exactly 1.0.

    When ``original_systems`` is supplied (recommended), uses **smart
    pin-and-redistribute** logic that matches the Streamlit UI behaviour:

    - Any weight you **changed** relative to the original is **locked** —
      its value is preserved exactly.
    - Only the **unchanged** weights are scaled proportionally to fill
      the remaining budget.

    This means: if you raise ``fault_monitoring`` from 0.28 → 0.30,
    that value stays at 0.30 and the other subsystems absorb the reduction.

    When ``original_systems`` is **not** supplied, falls back to simple
    proportional scaling of all weights.

    Parameters
    ----------
    systems:
        Edited list from :func:`weights_from_csv` or :func:`make_weight_update`.
        Not modified in-place — a deep copy is returned.
    original_systems:
        The unedited weights list (e.g. ``weights_result["weights"]``).
        Pass this to enable smart pin-and-redistribute.

    Returns
    -------
    New list of system dicts with all weights normalised to sum to 1.0.

    Raises
    ------
    ValueError
        If locked weights alone exceed 1.0 (impossible to redistribute),
        or if all weights in a group are 0.

    Example
    -------
    ::

        # Edit the CSV in Excel — change fault_monitoring from 0.28 → 0.30
        systems_from_csv = helpers.weights_from_csv(WEIGHTS_CSV)

        # Smart: locks 0.30, scales the other subsystems
        systems_normalised = helpers.normalize_weights(
            systems_from_csv,
            original_systems=weights_result["weights"],
        )
        updated = session.update_weights(
            systems_normalised,
            original_systems=weights_result["weights"],
        )

    """
    import copy

    result = copy.deepcopy(systems)

    TOL = 1e-9

    def _pin_redistribute(
        values: List[float], originals: Optional[List[float]]
    ) -> List[float]:
        """
        Redistribute values so they sum to 1.0.
        If originals given: lock changed indices, scale unchanged ones.
        Otherwise: proportional scale of all.
        """
        total = sum(values)
        if total == 0:
            return values

        if originals is None or len(originals) != len(values):
            # Simple proportional
            scale = 1.0 / total
            out = [round(v * scale, 6) for v in values]
        else:
            locked = [abs(values[i] - originals[i]) > TOL for i in range(len(values))]
            locked_sum = sum(v for v, lk in zip(values, locked) if lk)

            if locked_sum > 1.0 + TOL:
                raise ValueError(
                    f"Pinned weights sum to {locked_sum:.4f} which exceeds 1.0. "
                    "Please reduce some of the values you changed."
                )

            remaining = 1.0 - locked_sum
            unlocked_sum = sum(v for v, lk in zip(values, locked) if not lk)

            out = list(values)
            if not any(not lk for lk in locked):
                # All changed — proportional of everything
                scale = 1.0 / total if total > 0 else 1.0
                out = [round(v * scale, 6) for v in values]
            elif unlocked_sum > 0:
                scale = remaining / unlocked_sum
                out = [
                    round(values[i], 6) if locked[i] else round(values[i] * scale, 6)
                    for i in range(len(values))
                ]
            else:
                n_unlocked = sum(1 for lk in locked if not lk)
                share = remaining / n_unlocked if n_unlocked else 0
                out = [
                    round(values[i], 6) if locked[i] else round(share, 6)
                    for i in range(len(values))
                ]

        # Fix float residual on the largest value
        residual = round(1.0 - sum(out), 6)
        if residual:
            max_idx = out.index(max(out))
            out[max_idx] = round(out[max_idx] + residual, 6)
        return out

    # ── Build original lookup maps ────────────────────────────────────────────
    orig_sys_map: Dict[str, Dict] = {}
    if original_systems:
        for s in original_systems:
            orig_sys_map[s["system_name"]] = s

    # ── System-level normalisation ────────────────────────────────────────────
    sys_values = [float(s.get("weight", 0)) for s in result]
    orig_sys_values = (
        [
            float(
                orig_sys_map.get(s["system_name"], {}).get("weight", s.get("weight", 0))
            )
            for s in result
        ]
        if orig_sys_map
        else None
    )
    normalised_sys = _pin_redistribute(sys_values, orig_sys_values)
    for s, w in zip(result, normalised_sys):
        s["weight"] = w

    # ── Subsystem-level normalisation (per system) ────────────────────────────
    for s in result:
        subs = s.get("subsystems", [])
        if not subs:
            continue

        orig_sub_map: Dict[str, float] = {}
        if orig_sys_map and s["system_name"] in orig_sys_map:
            for sub in orig_sys_map[s["system_name"]].get("subsystems", []):
                orig_sub_map[sub["subsystem_name"]] = float(sub.get("weight", 0))

        sub_values = [float(sub.get("weight", 0)) for sub in subs]
        orig_sub_values = (
            [
                orig_sub_map.get(sub["subsystem_name"], sub.get("weight", 0))
                for sub in subs
            ]
            if orig_sub_map
            else None
        )

        if sum(sub_values) == 0:
            raise ValueError(
                f"System '{s.get('system_name', '?')}': all subsystem weights are 0."
            )

        normalised_subs = _pin_redistribute(sub_values, orig_sub_values)
        for sub, w in zip(subs, normalised_subs):
            sub["weight"] = w

    return result


def weights_to_csv(
    result: Union[str, Dict[str, Any]],
    path: str,
) -> str:
    """
    Export the weights from ``generate_weights()`` or ``update_weights()``
    to a flat CSV file for external editing (e.g. in Excel).

    CSV columns: ``system_name``, ``system_weight``, ``subsystem_name``, ``subsystem_weight``

    Each row represents one subsystem. The ``system_name`` and ``system_weight``
    columns repeat for each subsystem belonging to the same system — **only edit
    the weight columns**, not the name columns.

    After editing, load it back with :func:`weights_from_csv` and pass the
    result to ``session.update_weights()``.

    Parameters
    ----------
    result:
        The dict returned by ``generate_weights()`` / ``update_weights()``,
        or a path to the saved ``generate_weights.json`` artifact.
    path:
        File path to write the CSV (e.g. ``"artifacts/weights_draft.csv"``).

    Returns
    -------
    Absolute path of the written CSV file.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    import os

    data = _load_result(result)
    rows = []
    for sys_entry in data.get("weights", []):
        for sub in sys_entry.get("subsystems", []):
            rows.append(
                {
                    "system_name": sys_entry["system_name"],
                    "system_weight": round(sys_entry["weight"], 4),
                    "subsystem_name": sub["subsystem_name"],
                    "subsystem_weight": round(sub["weight"], 4),
                }
            )
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    df.to_csv(path, index=False)
    return os.path.abspath(path)


def weights_from_csv(path: str) -> List[Dict[str, Any]]:
    """
    Load an edited weights CSV and return a systems list ready for
    ``session.update_weights()``.

    The CSV must have columns:
    ``system_name``, ``system_weight``, ``subsystem_name``, ``subsystem_weight``

    The ``system_weight`` value is taken from the **first row** for each system
    (subsequent rows for the same system are ignored for the system-level weight).
    Subsystem weights are read per-row.

    Parameters
    ----------
    path:
        Path to the CSV file previously exported with :func:`weights_to_csv`.

    Returns
    -------
    List of system dicts compatible with ``session.update_weights(systems=...)``.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    df = pd.read_csv(path)
    required = {"system_name", "system_weight", "subsystem_name", "subsystem_weight"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing)}. "
            "Expected: system_name, system_weight, subsystem_name, subsystem_weight."
        )

    systems: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    inconsistent: List[str] = []
    for _, row in df.iterrows():
        sname = str(row["system_name"])
        sw = float(row["system_weight"])
        if sname not in seen:
            entry: Dict[str, Any] = {
                "system_name": sname,
                "weight": sw,
                "subsystems": [],
            }
            seen[sname] = entry
            systems.append(entry)
        elif abs(seen[sname]["weight"] - sw) > 1e-9:
            inconsistent.append(
                f"  '{sname}': first row has system_weight={seen[sname]['weight']}, "
                f"but another row has {sw}. Set the same value in all rows for this system."
            )
        seen[sname]["subsystems"].append(
            {
                "subsystem_name": str(row["subsystem_name"]),
                "weight": float(row["subsystem_weight"]),
            }
        )

    if inconsistent:
        raise ValueError(
            "Inconsistent system_weight values found — the same system must have "
            "the same system_weight in every row:\n" + "\n".join(inconsistent)
        )

    return systems


# ---------------------------------------------------------------------------
# Keyword frequency helpers
# Mirrors Streamlit labelling page: render_top_keywords_table()
# ---------------------------------------------------------------------------


def get_top_keywords_table(
    source: Union[str, Dict[str, Any], List[str]],
    top_n: int = 50,
) -> "pd.DataFrame":
    """
    Return a DataFrame of the top ``top_n`` keywords sorted by frequency.

    Parameters
    ----------
    source:
        One of:

        - The dict returned by ``session.extract_keywords()`` — frequencies are read
          from the ``keyword_pool`` field (available from the API since v2).
        - Path to an ``extract_keywords.json`` artifact — same lookup.
        - A bare ``{keyword: frequency}`` dict.
        - A plain ``List[str]`` of keywords (all frequencies shown as 1).

    top_n:
        Number of keywords to include (default 50).

    Returns
    -------
    pandas.DataFrame with columns ``["Keyword", "Frequency"]``.

    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    def _extract_freq(data: Dict[str, Any]) -> Dict[str, int]:
        """Pull frequency dict from an extract_keywords result or artifact."""
        kp = data.get("keyword_pool") or data.get("keywords_with_frequencies")
        if kp and isinstance(kp, dict):
            return {str(k): int(v) for k, v in kp.items()}
        # Fallback: plain keywords list → all frequencies = 1
        return {k: 1 for k in data.get("keywords", [])}

    if isinstance(source, list):
        freq: Dict[str, int] = {k: 1 for k in source}
    elif isinstance(source, str):
        freq = _extract_freq(_load_result(source))
    elif isinstance(source, dict):
        # Could be an extract_keywords() result (has "keywords" / "keyword_pool" keys)
        # or a bare {keyword: frequency} mapping passed directly.
        if "keywords" in source or "keyword_pool" in source:
            freq = _extract_freq(source)
        else:
            # Treat as a bare {keyword: frequency} dict — cast values to int defensively
            freq = {
                str(k): int(v) for k, v in source.items() if isinstance(v, (int, float))
            }
    else:
        raise TypeError(f"Unsupported source type: {type(source)}")

    # Sort descending by frequency; use keyword as secondary key for stable ordering
    top = sorted(freq.items(), key=lambda x: (x[1], x[0]), reverse=True)[:top_n]
    return pd.DataFrame(top, columns=["Keyword", "Frequency"])


def plot_top_keywords(
    source: Union[str, Dict[str, int], List[str]],
    top_n: int = 50,
    title: Optional[str] = None,
    width: int = 900,
    height: int = 600,
) -> None:
    """
    Horizontal bar chart of the top ``top_n`` keywords by frequency.

    Mirrors the keyword frequency chart on the Streamlit Data Labelling page.
    Bar height represents how many times the term appeared in the raw log text
    before any filtering.

    Parameters
    ----------
    source:
        The dict returned by ``session.extract_keywords()`` (preferred — real
        frequencies are read from ``keyword_pool``), a path to the saved
        ``extract_keywords.json`` artifact, a bare ``{keyword: frequency}`` dict,
        or a plain list of keywords (all bars equal height = 1).
    top_n:
        Number of keywords to display (default 50).
    title:
        Chart title.

    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly is required: pip install plotly")

    df = get_top_keywords_table(source, top_n=top_n)
    if df.empty:
        print("No keyword frequency data found in source.")
        return

    # Sort ascending so highest frequency is at the top of the chart
    df = df.sort_values("Frequency", ascending=True)

    fig = go.Figure(
        go.Bar(
            x=df["Frequency"].tolist(),
            y=df["Keyword"].tolist(),
            orientation="h",
            marker_color="#4a90d9",
            hovertemplate="<b>%{y}</b><br>Frequency: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title or f"Top {top_n} Keywords by Frequency", x=0.5),
        xaxis=dict(title="Frequency"),
        yaxis=dict(title="Keyword", automargin=True),
        width=width,
        height=height,
        margin=dict(l=200, r=40, t=60, b=60),
    )
    fig.show(renderer="notebook")


# ---------------------------------------------------------------------------
# Classification result distribution helpers
# Mirrors Streamlit labelling page: render_distribution_charts()
# Source: all_predictions_exploded.parquet (from run_classification zip)
# ---------------------------------------------------------------------------


def plot_classification_stacked(
    source: Union[str, "pd.DataFrame"],
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 550,
) -> None:
    """
    Stacked bar chart: x = system, stacked by subsystem, y = log count.

    Mirrors the "Stacked View" tab on the Streamlit labelling Classification
    Results page (``create_system_subsystem_stacked_chart``).

    Parameters
    ----------
    source:
        Path to ``all_predictions_exploded.parquet`` (inside the labelling zip,
        also at ``{artifact_dir}/labels/all_predictions_exploded.parquet``
        after ``run_classification``), or a DataFrame already loaded from it.

    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    df = _load_dataframe(source)
    df = (
        df[df.get("system_name", df.get("system", pd.Series(dtype=str))) != ""].copy()
        if "system_name" in df.columns
        else df.copy()
    )

    sys_col = "system_name" if "system_name" in df.columns else "system"
    sub_col = "subsystem_name" if "subsystem_name" in df.columns else "subsystem"

    if sys_col not in df.columns or sub_col not in df.columns:
        print(
            f"Source must have '{sys_col}' and '{sub_col}' columns. "
            f"Use all_predictions_exploded.parquet."
        )
        return

    df = df[df[sys_col].astype(str) != ""]
    grouped = df.groupby([sys_col, sub_col]).size().reset_index(name="count")
    systems = sorted(grouped[sys_col].unique())
    subsystems = sorted(grouped[sub_col].unique())

    fig = go.Figure()
    for sub in subsystems:
        sub_data = grouped[grouped[sub_col] == sub]
        counts = [int(sub_data[sub_data[sys_col] == s]["count"].sum()) for s in systems]
        if any(c > 0 for c in counts):
            fig.add_trace(
                go.Bar(
                    name=sub,
                    x=systems,
                    y=counts,
                    hovertemplate=f"<b>System:</b> %{{x}}<br><b>Subsystem:</b> {sub}"
                    "<br><b>Count:</b> %{y}<extra></extra>",
                )
            )

    fig.update_layout(
        barmode="stack",
        title=dict(text=title or "Log Distribution — Systems & Subsystems", x=0.5),
        xaxis=dict(title="System", tickangle=-35),
        yaxis=dict(title="Number of Logs"),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        width=width,
        height=height,
        margin=dict(l=60, r=200, t=60, b=100),
    )
    fig.show(renderer="notebook")


def plot_classification_by_system(
    source: Union[str, "pd.DataFrame"],
    title: Optional[str] = None,
    width: int = 900,
    height: int = 500,
) -> None:
    """
    Bar chart of log count per system.

    Mirrors the "By System" tab on the Streamlit labelling Classification
    Results page (``create_system_distribution_chart``).

    Parameters
    ----------
    source:
        Path to ``all_predictions_exploded.parquet`` or a DataFrame.

    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    df = _load_dataframe(source)
    sys_col = "system_name" if "system_name" in df.columns else "system"
    if sys_col not in df.columns:
        print(f"Source must have '{sys_col}' column.")
        return

    counts = (
        df[df[sys_col].astype(str) != ""][sys_col]
        .value_counts()
        .sort_values(ascending=False)
    )
    if counts.empty:
        print("No system data found.")
        return

    fig = go.Figure(
        go.Bar(
            x=counts.index.tolist(),
            y=counts.values.tolist(),
            marker_color="#2ecc71",
            text=counts.values.tolist(),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Logs: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title or "Log Distribution per System", x=0.5),
        xaxis=dict(title="System", tickangle=-35),
        yaxis=dict(title="Number of Logs"),
        width=width,
        height=height,
        margin=dict(l=60, r=40, t=60, b=120),
    )
    fig.show(renderer="notebook")


def plot_classification_by_subsystem(
    source: Union[str, "pd.DataFrame"],
    top_n: int = 20,
    title: Optional[str] = None,
    width: int = 900,
    height: int = 600,
) -> None:
    """
    Horizontal bar chart of top ``top_n`` subsystems by log count.

    Mirrors the "By Subsystem" tab on the Streamlit labelling Classification
    Results page (``create_subsystem_distribution_chart``).

    Parameters
    ----------
    source:
        Path to ``all_predictions_exploded.parquet`` or a DataFrame.
    top_n:
        Number of top subsystems to show (default 20).

    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    df = _load_dataframe(source)
    sub_col = "subsystem_name" if "subsystem_name" in df.columns else "subsystem"
    if sub_col not in df.columns:
        print(f"Source must have '{sub_col}' column.")
        return

    counts = (
        df[df[sub_col].astype(str) != ""][sub_col]
        .value_counts()
        .head(top_n)
        .sort_values(ascending=True)
    )
    if counts.empty:
        print("No subsystem data found.")
        return

    fig = go.Figure(
        go.Bar(
            x=counts.values.tolist(),
            y=counts.index.tolist(),
            orientation="h",
            marker_color="#9b59b6",
            text=counts.values.tolist(),
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Logs: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title or f"Top {top_n} Subsystems by Log Count", x=0.5),
        xaxis=dict(title="Number of Logs"),
        yaxis=dict(title="Subsystem", automargin=True),
        width=width,
        height=height,
        margin=dict(l=180, r=80, t=60, b=60),
    )
    fig.show(renderer="notebook")


# ---------------------------------------------------------------------------
# Risk breakdown helpers  (use after generate_risk_scores)
# ---------------------------------------------------------------------------


def list_risk_metrics(source: Union[str, "pd.DataFrame"]) -> List[str]:
    """
    Return all valid ``metric`` values for :func:`plot_risk_heatmap_multi_asset`.

    The list always starts with ``"operational_risk"`` followed by every
    ``{system}_system_risk`` column found in the parquet, sorted alphabetically.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.

    Returns
    -------
    List[str]
        e.g. ``['operational_risk', 'conveyor_handling_system_risk', ...]``

    Example
    -------
    >>> metrics = helpers.list_risk_metrics(parquet_path)
    >>> for m in metrics:
    ...     print(m)
    operational_risk
    communications_io_system_risk
    conveyor_handling_system_risk
    ...
    """
    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    df = _load_dataframe(source)
    system_cols = sorted([c for c in df.columns if c.endswith("_system_risk")])
    return ["operational_risk"] + system_cols


def get_risk_breakdown(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    date: str,
) -> dict:
    """
    Return a full risk breakdown for one asset on one date — no need to know
    the system or subsystem names in advance.

    The result contains:

    - ``operational_risk`` — overall aggregate score
    - ``systems``           — ``{system_name: score}`` dict for every system
    - ``subsystems``        — ``{system-subsystem: score}`` dict for every
      calibrated subsystem pair

    If the exact date is not available, the **closest** date in the parquet is
    used and a warning is printed.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet``, a CSV, or a DataFrame.
    asset_id:
        The asset to inspect (e.g. ``"K236"``).
    date:
        Date string in any common format (``"YYYY-MM-DD"``).

    Returns
    -------
    dict with keys ``asset_id``, ``date``, ``operational_risk``,
    ``systems``, ``subsystems``.

    Example
    -------
    >>> breakdown = helpers.get_risk_breakdown(parquet_path, "K236", "2025-01-09")
    >>> print(breakdown["operational_risk"])
    0.22
    >>> import json
    >>> print(json.dumps(breakdown, indent=2))
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required: pip install pandas")

    df = _load_dataframe(source)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    target = pd.to_datetime(date).date()

    # --- asset filter ---
    asset_df = df[df["asset_id"] == asset_id]
    if asset_df.empty:
        available = sorted(df["asset_id"].unique().tolist())
        raise ValueError(
            f"asset_id '{asset_id}' not found.\n" f"Available asset IDs: {available}"
        )

    # --- closest date ---
    available_dates = sorted(asset_df["date"].unique())
    if target not in available_dates:
        target = min(available_dates, key=lambda d: abs((d - target).days))
        print(f"Exact date not found — using closest available date: {target}")

    # --- aggregate (max) across rows for the same asset+date ---
    day_df = asset_df[asset_df["date"] == target]
    row = day_df.max(numeric_only=True)

    # --- system risks ---
    system_cols = sorted([c for c in df.columns if c.endswith("_system_risk")])
    systems: Dict[str, float] = {}
    for c in system_cols:
        system_name = c.replace("_system_risk", "")
        systems[system_name] = round(float(row.get(c, 0) or 0), 2)

    # --- subsystem risks (calibrated columns) ---
    subsystem_cols = sorted([c for c in df.columns if c.endswith("_calibrated_risk")])
    subsystems: Dict[str, float] = {}
    for c in subsystem_cols:
        pair = c.replace(
            "_calibrated_risk", ""
        )  # e.g. "data_communications-message_handling"
        subsystems[pair] = round(float(row.get(c, 0) or 0), 2)

    return {
        "asset_id": asset_id,
        "date": str(target),
        "operational_risk": round(float(row.get("operational_risk", 0) or 0), 2),
        "systems": systems,
        "subsystems": subsystems,
    }


# ---------------------------------------------------------------------------
# Training validation helpers  (use after train_risk_model)
# ---------------------------------------------------------------------------


def plot_threshold_summary(
    thresholds_source: Union[str, Dict[str, Any]],
    training_fe_source: Union[str, "pd.DataFrame"],
    systems: Optional[List[str]] = None,
    title: str = "Calibration Threshold Summary",
    width: int = 1000,
    height: int = 500,
) -> None:
    """
    Overlaid bar chart showing each subsystem's calibration threshold alongside
    its mean and max from the training feature data.

    Lets you quickly sanity-check whether thresholds are reasonable — a threshold
    close to the max suggests the quantile is very high; one close to the mean
    suggests a tight distribution.

    Parameters
    ----------
    thresholds_source:
        Path to ``calibration_thresholds.json`` or the dict itself.
    training_fe_source:
        Path to ``training_fe.parquet`` or a DataFrame already loaded from it.
    systems:
        Optional list of system names (e.g. ``["motion_control", "hydraulics"]``)
        to restrict the chart to subsystems belonging to those systems.
        Defaults to all systems.
    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    thresholds = (
        _load_result(thresholds_source)
        if isinstance(thresholds_source, str)
        else thresholds_source
    )
    fe_df = _load_dataframe(training_fe_source)

    def _matches_systems(pair: str) -> bool:
        if systems is None:
            return True
        return any(pair.startswith(f"{s}-") for s in systems)

    feat_cols = {
        p: f"{p}_risk_feature"
        for p in thresholds
        if f"{p}_risk_feature" in fe_df.columns and _matches_systems(p)
    }
    if not feat_cols:
        print(
            "No '_risk_feature' columns found in training_fe. Check the parquet columns."
        )
        return

    rows = []
    for pair, col in feat_cols.items():
        series = fe_df[col].dropna()
        rows.append(
            {
                "subsystem": pair,
                "threshold": thresholds[pair],
                "mean": round(float(series.mean()), 2),
                "max": round(float(series.max()), 2),
            }
        )
    rows.sort(key=lambda r: r["threshold"], reverse=True)

    labels = [r["subsystem"] for r in rows]
    thresholds_ = [r["threshold"] for r in rows]
    means = [r["mean"] for r in rows]
    maxes = [r["max"] for r in rows]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Max (training)",
            x=labels,
            y=maxes,
            marker_color="#e0e0e0",
            hovertemplate="%{x}<br>Max: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Mean (training)",
            x=labels,
            y=means,
            marker_color="#7fb3d3",
            hovertemplate="%{x}<br>Mean: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            name="Threshold",
            x=labels,
            y=thresholds_,
            marker_color="#e74c3c",
            opacity=0.7,
            hovertemplate="%{x}<br>Threshold: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="overlay",
        title=dict(text=title, x=0.5),
        xaxis=dict(title="Subsystem", tickangle=-45),
        yaxis=dict(title="Feature Value"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        width=width,
        height=height,
        margin=dict(l=60, r=40, t=80, b=150),
    )
    fig.show(renderer="notebook")


def plot_feature_distributions(
    training_fe_source: Union[str, "pd.DataFrame"],
    thresholds_source: Union[str, Dict[str, Any]],
    systems: Optional[List[str]] = None,
    max_cols: int = 3,
    bins: int = 30,
    width: int = 1100,
    row_height: int = 280,
) -> None:
    """
    Grid of histograms — one per subsystem — showing the distribution of each
    ``_risk_feature`` column with the calibration threshold as a vertical red line.

    Tells you where the threshold sits in the training distribution and how
    spread out the feature values are.

    Parameters
    ----------
    training_fe_source:
        Path to ``training_fe.parquet`` or a DataFrame.
    thresholds_source:
        Path to ``calibration_thresholds.json`` or the dict itself.
    systems:
        Optional list of system names (e.g. ``["motion_control", "hydraulics"]``)
        to restrict the grid to subsystems belonging to those systems.
        Defaults to all systems.
    max_cols:
        Number of columns in the subplot grid (default 3).
    bins:
        Number of histogram bins (default 30).
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    thresholds = (
        _load_result(thresholds_source)
        if isinstance(thresholds_source, str)
        else thresholds_source
    )
    fe_df = _load_dataframe(training_fe_source)

    pairs = [
        p
        for p in thresholds
        if f"{p}_risk_feature" in fe_df.columns
        and (systems is None or any(p.startswith(f"{s}-") for s in systems))
    ]
    if not pairs:
        print("No '_risk_feature' columns found. Check parquet columns.")
        return

    n_rows = -(-len(pairs) // max_cols)
    fig = make_subplots(
        rows=n_rows,
        cols=max_cols,
        subplot_titles=[p.replace("-", " — ").replace("_", " ").title() for p in pairs],
    )

    for i, pair in enumerate(pairs):
        row = i // max_cols + 1
        col = i % max_cols + 1
        values = fe_df[f"{pair}_risk_feature"].dropna().tolist()
        threshold = thresholds[pair]

        fig.add_trace(
            go.Histogram(
                x=values,
                nbinsx=bins,
                marker_color="#7fb3d3",
                showlegend=False,
                hovertemplate="Value: %{x}<br>Count: %{y}<extra></extra>",
            ),
            row=row,
            col=col,
        )

        fig.add_vline(
            x=threshold,
            line=dict(color="#e74c3c", width=2, dash="dash"),
            row=row,
            col=col,
            annotation_text=f"threshold={threshold}",
            annotation_position="top right",
            annotation_font_size=9,
        )

    fig.update_layout(
        title=dict(text="Feature Distributions vs Calibration Thresholds", x=0.5),
        width=width,
        height=row_height * n_rows + 80,
        margin=dict(l=40, r=40, t=80, b=40),
    )
    fig.show(renderer="notebook")


def plot_feature_timeseries(
    training_fe_source: Union[str, "pd.DataFrame"],
    thresholds_source: Union[str, Dict[str, Any]],
    asset_id: Union[str, List[str]],
    system: str,
    subsystem: str,
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 420,
) -> None:
    """
    Time series of a subsystem's rolling risk feature for one or more assets,
    with the calibration threshold shown as a horizontal dashed line.

    Each asset gets its own line. Lets you compare activity patterns across
    assets and judge whether the threshold makes sense.

    Parameters
    ----------
    training_fe_source:
        Path to ``training_fe.parquet`` or a DataFrame.
    thresholds_source:
        Path to ``calibration_thresholds.json`` or the dict itself.
    asset_id:
        A single asset ID string, or a list of asset ID strings.
    system:
        System name (e.g. ``"motion_control"``).
    subsystem:
        Subsystem name (e.g. ``"datum_control"``).
    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    thresholds = (
        _load_result(thresholds_source)
        if isinstance(thresholds_source, str)
        else thresholds_source
    )
    fe_df = _load_dataframe(training_fe_source)

    pair = f"{system}-{subsystem}"
    feat_col = f"{pair}_risk_feature"

    if feat_col not in fe_df.columns:
        available = [
            c.replace("_risk_feature", "")
            for c in fe_df.columns
            if c.endswith("_risk_feature")
        ]
        print(f"Feature column '{feat_col}' not found.\nAvailable pairs: {available}")
        return

    asset_ids = [asset_id] if isinstance(asset_id, str) else list(asset_id)

    # Distinct colours for up to ~20 assets; cycle beyond that
    _palette = [
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#f39c12",
        "#1abc9c",
        "#e67e22",
        "#34495e",
        "#16a085",
        "#8e44ad",
        "#d35400",
        "#27ae60",
        "#2980b9",
        "#c0392b",
        "#7f8c8d",
        "#f1c40f",
        "#6c5ce7",
        "#00b894",
        "#fd79a8",
        "#e17055",
        "#74b9ff",
    ]

    fig = go.Figure()
    found_any = False

    for i, aid in enumerate(asset_ids):
        asset_df = fe_df[fe_df["asset_id"].astype(str) == str(aid)].sort_values("date")
        if asset_df.empty:
            print(f"Asset '{aid}' not found — skipping.")
            continue
        found_any = True
        color = _palette[i % len(_palette)]
        dates = [str(d) for d in asset_df["date"]]
        values = asset_df[feat_col].tolist()
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines+markers",
                name=str(aid),
                line=dict(color=color, width=2),
                marker=dict(size=4),
                hovertemplate=f"Asset: {aid}<br>%{{x}}<br>Feature: %{{y:.2f}}<extra></extra>",
            )
        )

    if not found_any:
        print(
            f"None of the requested assets were found. Available: {list(fe_df['asset_id'].unique()[:10])}"
        )
        return

    threshold = thresholds.get(pair)
    if threshold is not None:
        fig.add_hline(
            y=threshold,
            line=dict(color="#e74c3c", width=2, dash="dash"),
            annotation_text=f"threshold = {threshold}",
            annotation_position="top right",
            annotation_font_size=10,
        )

    asset_label = asset_ids[0] if len(asset_ids) == 1 else f"{len(asset_ids)} assets"
    fig.update_layout(
        title=dict(
            text=title
            or f"{pair.replace('-', ' — ').replace('_', ' ').title()} — {asset_label}",
            x=0.5,
        ),
        xaxis=dict(title="Date", tickangle=-45),
        yaxis=dict(title="Risk Feature Value"),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        width=width,
        height=height,
        margin=dict(l=60, r=120, t=60, b=80),
    )
    fig.show(renderer="notebook")


def plot_feature_breakdown(
    training_fe_source: Union[str, "pd.DataFrame"],
    thresholds_source: Union[str, Dict[str, Any]],
    asset_id: str,
    system: str,
    subsystem: str,
    is_free_text: bool = True,
    logs_mapping: Union[str, Dict[str, List[str]], None] = None,
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 650,
) -> None:
    """
    Two-panel chart showing how the risk feature is built up for a single asset
    and subsystem over time.

    **Free-text mode** (``is_free_text=True``):

    - Top: risk feature line + threshold
    - Bottom: raw daily event count for that subsystem (the source that feeds
      binary → rolling → risk feature)

    **Fixed-log mode** (``is_free_text=False``):

    - Top: risk feature line + threshold
    - Bottom: stacked bars of the rolling features per individual log code that
      belong to this subsystem — these are what sum into the risk feature.
      Requires ``logs_mapping``.

    Parameters
    ----------
    training_fe_source:
        Path to ``training_fe.parquet`` or a DataFrame.
    thresholds_source:
        Path to ``calibration_thresholds.json`` or the dict itself.
    asset_id:
        Asset to inspect.
    system:
        System name (e.g. ``"motion_control"``).
    subsystem:
        Subsystem name (e.g. ``"datum_control"``).
    is_free_text:
        ``True`` for free-text (semantic classification) datasets,
        ``False`` for fixed-log (exact-match) datasets.
    logs_mapping:
        **Fixed-log mode only.** Path to ``logs_by_system_subsystem.json`` or
        the dict itself. Maps ``"{system}-{subsystem}"`` → list of log code
        strings. Required when ``is_free_text=False``.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    thresholds = (
        _load_result(thresholds_source)
        if isinstance(thresholds_source, str)
        else thresholds_source
    )
    fe_df = _load_dataframe(training_fe_source)

    pair = f"{system}-{subsystem}"
    feat_col = f"{pair}_risk_feature"

    if feat_col not in fe_df.columns:
        available = [
            c.replace("_risk_feature", "")
            for c in fe_df.columns
            if c.endswith("_risk_feature")
        ]
        print(f"Feature column '{feat_col}' not found.\nAvailable pairs: {available}")
        return

    asset_df = fe_df[fe_df["asset_id"].astype(str) == str(asset_id)].sort_values("date")
    if asset_df.empty:
        print(
            f"Asset '{asset_id}' not found. Available: {list(fe_df['asset_id'].unique()[:10])}"
        )
        return

    dates = [str(d) for d in asset_df["date"]]
    threshold = thresholds.get(pair)

    _palette = [
        "#3498db",
        "#2ecc71",
        "#9b59b6",
        "#f39c12",
        "#1abc9c",
        "#e67e22",
        "#34495e",
        "#16a085",
        "#8e44ad",
        "#d35400",
        "#27ae60",
        "#2980b9",
        "#c0392b",
        "#7f8c8d",
        "#f1c40f",
        "#6c5ce7",
        "#00b894",
        "#fd79a8",
        "#e17055",
        "#74b9ff",
    ]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.4, 0.3, 0.3],
        vertical_spacing=0.08,
        subplot_titles=[
            f"{pair.replace('-', ' — ').replace('_', ' ').title()} — Risk Feature",
            (
                "Rolling Features per Log Code"
                if not is_free_text
                else "Raw Daily Event Count"
            ),
            (
                "Binary Features per Log Code"
                if not is_free_text
                else "Binary Event Indicator"
            ),
        ],
    )

    # ── Row 1: risk feature + threshold ──────────────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=asset_df[feat_col].tolist(),
            mode="lines+markers",
            name="Risk Feature",
            line=dict(color="#3498db", width=2),
            marker=dict(size=4),
            hovertemplate="%{x}<br>Risk Feature: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if threshold is not None:
        fig.add_hline(
            y=threshold,
            line=dict(color="#e74c3c", width=2, dash="dash"),
            row=1,
            col=1,
            annotation_text=f"threshold = {threshold}",
            annotation_position="top right",
            annotation_font_size=10,
        )

    # ── Rows 2 & 3 ───────────────────────────────────────────────────────────
    if is_free_text:
        # Row 2: raw daily count
        if pair in asset_df.columns:
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=asset_df[pair].tolist(),
                    name="Daily Count",
                    showlegend=False,
                    marker_color="#7fb3d3",
                    hovertemplate="%{x}<br>Count: %{y}<extra></extra>",
                ),
                row=2,
                col=1,
            )
        else:
            print(f"Raw count column '{pair}' not found — row 2 skipped.")

        # Row 3: binary indicator
        binary_col = f"binary_{pair}"
        if binary_col in asset_df.columns:
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=asset_df[binary_col].tolist(),
                    name="Binary",
                    showlegend=False,
                    marker_color="#e67e22",
                    hovertemplate="%{x}<br>Binary: %{y}<extra></extra>",
                ),
                row=3,
                col=1,
            )
        else:
            print(f"Binary column '{binary_col}' not found — row 3 skipped.")

    else:
        # Fixed-log: need logs_mapping
        if logs_mapping is None:
            print(
                "Fixed-log mode requires logs_mapping.\n"
                "Pass logs_mapping=result['logs_mapping_path'] or the path to "
                "logs_by_system_subsystem.json."
            )
        else:
            if isinstance(logs_mapping, str):
                with open(logs_mapping) as fh:
                    mapping: Dict[str, List[str]] = _json.load(fh)
            else:
                mapping = logs_mapping

            log_codes = mapping.get(pair, [])

            # Auto-detect rolling prefix from first matching log code
            rolling_prefix = None
            for lc in log_codes:
                candidates = [
                    c
                    for c in fe_df.columns
                    if c.endswith(f"_binary_{lc}") and c.startswith("rolling_")
                ]
                if candidates:
                    rolling_prefix = candidates[0][: -len(f"_binary_{lc}")]
                    break

            rolling_found = 0
            binary_found = 0

            for i, lc in enumerate(log_codes):
                color = _palette[i % len(_palette)]
                label = (lc[:40] + "...") if len(lc) > 40 else lc

                # Row 2: rolling features
                if rolling_prefix:
                    roll_col = f"{rolling_prefix}_binary_{lc}"
                    if roll_col in asset_df.columns:
                        fig.add_trace(
                            go.Bar(
                                x=dates,
                                y=asset_df[roll_col].fillna(0).tolist(),
                                name=label,
                                marker_color=color,
                                legendgroup=lc,
                                hovertemplate=f"<b>{lc}</b><br>%{{x}}<br>Rolling: %{{y:.2f}}<extra></extra>",
                            ),
                            row=2,
                            col=1,
                        )
                        rolling_found += 1

                # Row 3: binary features
                bin_col = f"binary_{lc}"
                if bin_col in asset_df.columns:
                    fig.add_trace(
                        go.Bar(
                            x=dates,
                            y=asset_df[bin_col].fillna(0).tolist(),
                            name=label,
                            marker_color=color,
                            legendgroup=lc,
                            showlegend=(
                                rolling_found == 0
                            ),  # avoid duplicate legend entries
                            hovertemplate=f"<b>{lc}</b><br>%{{x}}<br>Binary: %{{y}}<extra></extra>",
                        ),
                        row=3,
                        col=1,
                    )
                    binary_found += 1

            if rolling_found == 0:
                print(f"No rolling columns found for '{pair}' — row 2 skipped.")
            if binary_found == 0:
                print(f"No binary columns found for '{pair}' — row 3 skipped.")
            if rolling_found > 0 or binary_found > 0:
                fig.update_layout(barmode="stack")

    chart_title = (
        title
        or f"{pair.replace('-', ' — ').replace('_', ' ').title()} — Feature Breakdown — {asset_id}"
    )
    fig.update_layout(
        title=dict(text=chart_title, x=0.5),
        xaxis3=dict(title="Date", tickangle=-45),
        yaxis=dict(title="Risk Feature"),
        yaxis2=dict(title="Rolling Value"),
        yaxis3=dict(title="Binary (0/1)"),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        width=width,
        height=height,
        margin=dict(l=60, r=180, t=80, b=80),
    )
    fig.show(renderer="notebook")


def plot_operational_risk_breakdown(
    source: Union[str, "pd.DataFrame"],
    asset_id: str,
    model_config: Union[str, Dict[str, Any]],
    title: Optional[str] = None,
    width: int = 1000,
    height: int = 600,
) -> None:
    """
    Single-panel chart for a single asset showing system weighted contributions
    as stacked bars with the operational risk line tracing the top of the stack.

    Each bar segment = ``{system}_system_risk × weight``. The operational risk
    line sits on top, forming a border around the stack.

    Parameters
    ----------
    source:
        Path to ``risk_scores.parquet`` or a DataFrame.
    asset_id:
        Asset to inspect.
    model_config:
        Path to ``model_config.json`` or the dict itself. Must contain a
        ``"system_weights"`` key mapping system names to their weights.
    title:
        Chart title. Defaults to ``"Operational Risk Breakdown — {asset_id}"``.
    """
    try:
        import plotly.graph_objects as go
        import pandas as pd
    except ImportError:
        raise ImportError("plotly and pandas are required: pip install plotly pandas")

    cfg = _load_result(model_config) if isinstance(model_config, str) else model_config
    system_weights: Dict[str, float] = cfg.get("system_weights", {})
    if not system_weights:
        print("'system_weights' not found in model_config.")
        return

    df = _load_dataframe(source)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    asset_df = df[df["asset_id"].astype(str) == str(asset_id)].sort_values("date")
    if asset_df.empty:
        print(f"Asset '{asset_id}' not found. Available: {list(df['asset_id'].unique()[:10])}")
        return

    daily = asset_df.groupby("date").max().reset_index()
    dates = [str(d) for d in daily["date"]]

    _palette = [
        "#3498db", "#2ecc71", "#9b59b6", "#f39c12", "#1abc9c",
        "#e67e22", "#34495e", "#16a085", "#8e44ad", "#d35400",
        "#27ae60", "#2980b9", "#c0392b", "#7f8c8d", "#f1c40f",
    ]

    fig = go.Figure()

    # ── Stacked bars: weighted system contributions ───────────────────────────
    found = 0
    for i, (system, weight) in enumerate(system_weights.items()):
        risk_col = f"{system}_system_risk"
        if risk_col not in daily.columns:
            continue
        weighted = (daily[risk_col].fillna(0) * weight).tolist()
        label = system.replace("_", " ").title()
        fig.add_trace(go.Bar(
            x=dates,
            y=weighted,
            name=label,
            marker_color=_palette[found % len(_palette)],
            hovertemplate=f"<b>{label}</b><br>%{{x}}<br>Contribution: %{{y:.2f}}<extra></extra>",
        ))
        found += 1

    if found == 0:
        print("No system risk columns found in the DataFrame matching model_config system_weights.")
        return

    # ── Operational risk line on top ──────────────────────────────────────────
    if "operational_risk" in daily.columns:
        fig.add_trace(go.Scatter(
            x=dates,
            y=daily["operational_risk"].tolist(),
            mode="lines",
            name="Operational Risk",
            line=dict(color="#2c3e50", width=2.5),
            hovertemplate="%{x}<br>Operational Risk: %{y:.1f}<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(text=title or f"Operational Risk Breakdown — {asset_id}", x=0.5),
        xaxis=dict(title="Date", tickangle=-45),
        yaxis=dict(title="Risk Score"),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        width=width,
        height=height,
        margin=dict(l=60, r=160, t=80, b=80),
    )
    fig.show(renderer="notebook")
