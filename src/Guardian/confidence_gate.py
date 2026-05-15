"""Gate 2 of the Triple-Gate pipeline: ML confidence filter.

Loads a persisted Guardian artefact (model + isotonic calibrator) and
gates each cycle on calibrated p̂ > threshold.

AGENTS.md §3.3: the 0.85 threshold is LOCKED — agents cannot change it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import structlog

from src.guardian.features import FEATURE_ORDER

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ConfidenceGateResult:
    passed: bool
    p_hat: float
    threshold: float
    rejection_reason: str | None


class ConfidenceGate:
    """Production wrapper around a trained Guardian artefact."""

    def __init__(self, artifact_path: Path, threshold: float = 0.85) -> None:
        bundle = joblib.load(artifact_path)
        self.model = bundle["model"]
        self.calibrator = bundle["calibrator"]
        self.threshold = threshold

    def evaluate(self, features: dict[str, float]) -> ConfidenceGateResult:
        x = [features[k] for k in FEATURE_ORDER]
        raw = self.model.predict_proba([x])[0, 1]
        p_hat = float(self.calibrator.transform([raw])[0])
        passed = p_hat > self.threshold
        return ConfidenceGateResult(
            passed=passed,
            p_hat=p_hat,
            threshold=self.threshold,
            rejection_reason=None if passed else "p_hat_below_threshold",
        )
