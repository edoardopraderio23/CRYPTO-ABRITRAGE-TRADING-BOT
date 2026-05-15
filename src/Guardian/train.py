"""Training pipeline for the Guardian.

Trains LightGBM (production) + Random Forest (interpretable baseline),
calibrates each via isotonic regression, picks the decision threshold,
and persists the bundle to a joblib artefact.

Reference: TECHNICAL_PLAN.md §5 (Model) and §8 (Backtest design).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import structlog
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import precision_recall_curve, roc_auc_score

from src.guardian.features import FEATURE_ORDER

log = structlog.get_logger(__name__)

DEFAULT_DECISION_THRESHOLD: float = 0.85
DEFAULT_MIN_RECALL: float = 0.30


@dataclass(frozen=True)
class TrainResult:
    version: str
    algo: str
    val_auc: float
    val_precision_at_threshold: float
    val_recall_at_threshold: float
    decision_threshold: float
    artifact_path: Path


def walk_forward_split(
    n: int, train_frac: float = 0.70, val_frac: float = 0.15,
) -> tuple[range, range, range]:
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return range(0, train_end), range(train_end, val_end), range(val_end, n)


def train_lightgbm(X: np.ndarray, y: np.ndarray) -> lgb.LGBMClassifier:
    clf = lgb.LGBMClassifier(
        objective="binary", n_estimators=200, learning_rate=0.05,
        max_depth=6, num_leaves=31, min_child_samples=20,
        random_state=42, verbose=-1,
    )
    clf.fit(X, y)
    return clf


def train_random_forest(X: np.ndarray, y: np.ndarray) -> RandomForestClassifier:
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=10, min_samples_leaf=5,
        random_state=42, n_jobs=-1,
    )
    clf.fit(X, y)
    return clf


def calibrate(raw_val: np.ndarray, y_val: np.ndarray) -> IsotonicRegression:
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_val, y_val)
    return iso


def choose_threshold(
    calibrated_val: np.ndarray,
    y_val: np.ndarray,
    min_recall: float = DEFAULT_MIN_RECALL,
) -> float:
    _, recall, thresholds = precision_recall_curve(y_val, calibrated_val)
    valid = [t for t, r in zip(thresholds, recall[:-1]) if r >= min_recall]
    if not valid:
        log.warning("guardian.no_threshold_meets_recall", min_recall=min_recall)
        return DEFAULT_DECISION_THRESHOLD
    return float(max(valid))


def run_training(
    X: np.ndarray,
    y: np.ndarray,
    algo: str = "lightgbm",
    artifact_dir: Path = Path("models"),
) -> TrainResult:
    n = len(y)
    train_idx, val_idx, _ = walk_forward_split(n)
    X_train, y_train = X[list(train_idx)], y[list(train_idx)]
    X_val, y_val = X[list(val_idx)], y[list(val_idx)]

    if algo == "lightgbm":
        model = train_lightgbm(X_train, y_train)
    elif algo == "random_forest":
        model = train_random_forest(X_train, y_train)
    else:
        raise ValueError(f"Unknown algo: {algo}")

    raw_val = model.predict_proba(X_val)[:, 1]
    iso = calibrate(raw_val, y_val)
    cal_val = iso.transform(raw_val)

    val_auc = float(roc_auc_score(y_val, cal_val))
    threshold = choose_threshold(cal_val, y_val)

    pred = (cal_val >= threshold).astype(int)
    tp = int(((pred == 1) & (y_val == 1)).sum())
    precision = tp / max(int(pred.sum()), 1)
    recall = tp / max(int(y_val.sum()), 1)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    version = f"v0.1.0-{algo}-{stamp}"
    artifact_path = artifact_dir / f"{version}.joblib"
    joblib.dump(
        {"model": model, "calibrator": iso, "feature_order": FEATURE_ORDER},
        artifact_path,
    )

    log.info(
        "guardian.training_complete",
        version=version, algo=algo,
        val_auc=val_auc, val_precision=precision,
        val_recall=recall, threshold=threshold,
    )

    return TrainResult(
        version=version, algo=algo,
        val_auc=val_auc,
        val_precision_at_threshold=precision,
        val_recall_at_threshold=recall,
        decision_threshold=threshold,
        artifact_path=artifact_path,
    )
