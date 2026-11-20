"""Build a scoring bundle for a deployed model.

A deployed model scores new logs repeatedly without a session. It needs only
part of ``complete_model_<id>.zip``: settings, the system/subsystem
structure, weights, calibration thresholds, and the log-code map (fixed-log)
or keyword index (free-text). :func:`build_scoring_bundle` copies just those
parts into a small bundle zip **on your machine**. The raw logs, failures,
scores and predictions in the model zip are never uploaded.

What the bundle contains (and so what Amygda stores for a hosted
deployment): log codes or keywords, system and subsystem names, weights and
thresholds. No asset IDs, timestamps or log rows.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

BUNDLE_FORMAT_VERSION = 1
MANIFEST = "bundle.json"
CODE_MAP_LABEL_COLUMNS = ["system_name", "subsystem_name", "system_subsystem_pair"]


def content_hash(files: Dict[str, bytes]) -> str:
    """Hash of every bundle file except the manifest (matches the server)."""
    h = hashlib.sha256()
    for name in sorted(n for n in files if n != MANIFEST):
        h.update(name.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(files[name]).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()


def _sdk_version() -> str:
    from amygda_ops_risk_score import __version__

    return __version__


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    return json.loads(zf.read(name))


def _require(zf: zipfile.ZipFile, names: set, path: str, hint: str) -> None:
    if path not in names:
        from amygda_ops_risk_score.exceptions import ValidationError

        raise ValidationError(
            f"{os.path.basename(zf.filename or 'model zip')} has no {path}. {hint}"
        )


def is_scoring_bundle(path: str) -> bool:
    """True if ``path`` is a bundle zip (has bundle.json at its root)."""
    try:
        with zipfile.ZipFile(path) as zf:
            return MANIFEST in zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def build_scoring_bundle(model_zip: str, dest_path: Optional[str] = None) -> str:
    """Build a scoring bundle from a trained model zip.

    Args:
        model_zip:
            ``complete_model_<id>.zip`` downloaded by ``generate_risk_scores``
            (or any zip with a trained risk model in it).
        dest_path:
            Where to write the bundle. Defaults to ``<model_zip>_bundle.zip``
            next to the model zip.

    Returns:
        The bundle's path. Inspect it with :func:`describe_bundle`.

    Raises:
        ValidationError: the zip has no trained risk model in it.
    """
    from amygda_ops_risk_score.exceptions import ValidationError

    if not os.path.isfile(model_zip):
        raise ValidationError(f"Model zip not found: {model_zip}")
    try:
        zf = zipfile.ZipFile(model_zip)
    except zipfile.BadZipFile:
        raise ValidationError(f"{model_zip} is not a zip file.")

    with zf:
        names = set(zf.namelist())
        if MANIFEST in names:
            raise ValidationError(f"{model_zip} is already a scoring bundle.")
        train_hint = (
            "Use the complete_model zip from a session where the risk model was "
            "trained (configure_training and train_risk_model)."
        )
        _require(
            zf, names, "outputs/model_config.json", "Run the labelling pipeline first."
        )
        for path in (
            "risk_score/risk_score_config.json",
            "risk_score/calibration_thresholds.json",
            "labels/accepted_hierarchy.json",
        ):
            _require(zf, names, path, train_hint)

        model_config = _read_json(zf, "outputs/model_config.json")
        risk_config = _read_json(zf, "risk_score/risk_score_config.json")
        free_text = bool(model_config.get("is_free_text", True))
        weights_source = risk_config.get("weights_source", "labelling")

        if weights_source == "supervised":
            _require(zf, names, "risk_score/trained_weights.json", train_hint)
            w = _read_json(zf, "risk_score/trained_weights.json")
        else:
            w = model_config
        weights = {
            "system_weights": w["system_weights"],
            "subsystem_weights": w["subsystem_weights"],
        }
        hierarchy = [
            {
                "system": r.get("system"),
                "subsystem": r.get("subsystem"),
                "system_subsystem_pair": r["system_subsystem_pair"],
            }
            for r in _read_json(zf, "labels/accepted_hierarchy.json")
        ]

        files: Dict[str, bytes] = {
            "hierarchy.json": json.dumps(hierarchy, indent=1).encode(),
            "weights.json": json.dumps(weights, indent=1).encode(),
            "thresholds.json": zf.read("risk_score/calibration_thresholds.json"),
        }

        settings: Dict[str, Any] = {
            "format_version": BUNDLE_FORMAT_VERSION,
            "sdk_version": _sdk_version(),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "is_free_text": free_text,
            "log_column": model_config["log_column"],
            "asset_id_mapping": risk_config["asset_id_mapping"],
            "timestamp_mapping": risk_config["timestamp_mapping"],
            "date_format": risk_config.get("date_format", "infer"),
            "rolling_window": risk_config["rolling_window"],
            "rolling_feature_type": risk_config["rolling_feature_type"],
            "feature_frequency": risk_config.get("feature_frequency", "1D"),
            "weights_source": weights_source,
        }

        if free_text:
            collection = model_config["qdrant_collection_name"]
            src = "classification_models/qdrant_storage"
            for rel in ("meta.json", f"collection/{collection}/storage.sqlite"):
                _require(
                    zf, names, f"{src}/{rel}", "The free-text keyword index is missing."
                )
                files[f"qdrant/{rel}"] = zf.read(f"{src}/{rel}")
            settings["qdrant_collection_name"] = collection
            settings["similarity_threshold"] = float(
                model_config.get("similarity_threshold", 0.4)
            )
        else:
            import pandas as pd

            _require(
                zf,
                names,
                "labels/deduplicated_predictions.parquet",
                "Run the labelling pipeline first.",
            )
            preds = pd.read_parquet(
                io.BytesIO(zf.read("labels/deduplicated_predictions.parquet"))
            )
            log_column = model_config["log_column"]
            # Codes and labels only: asset IDs, timestamps and keywords are dropped.
            code_map = (
                preds[[log_column] + CODE_MAP_LABEL_COLUMNS]
                .drop_duplicates(subset=[log_column])
                .reset_index(drop=True)
            )
            buf = io.BytesIO()
            code_map.to_parquet(buf, index=False)
            files["code_map.parquet"] = buf.getvalue()

    settings["content_hash"] = content_hash(files)
    files[MANIFEST] = json.dumps(settings, indent=1).encode()

    if dest_path is None:
        base = model_zip[:-4] if model_zip.lower().endswith(".zip") else model_zip
        dest_path = f"{base}_bundle.zip"
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as out:
        for name in sorted(files):
            out.writestr(name, files[name])
    return dest_path


def describe_bundle(bundle_path: str) -> Dict[str, Any]:
    """Return a bundle's settings and file list, to check what will be uploaded."""
    with zipfile.ZipFile(bundle_path) as zf:
        settings = json.loads(zf.read(MANIFEST))
        files = {i.filename: i.file_size for i in zf.infolist() if not i.is_dir()}
    return {"settings": settings, "files": files, "bytes": os.path.getsize(bundle_path)}
