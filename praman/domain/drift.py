"""
Drift detection scoring and circuit breaker logic.

Responsibility
    Compute drift scores (three independent detectors behind one interface).
    Determine if drift exceeds threshold (trip the circuit breaker).
    Log drift events as evidence (circuit breaker halt is itself logged).

Must not
    Perform I/O or network calls (adapters handle external APIs).
    Know about the database or ledger directly (repositories handle that).
    Make policy decisions (that is PolicyEngine's job).

Design notes
    Three detectors:
    1. Deterministic stub (v0.1.0) — reproducible but measures nothing
    2. PSI (Population Stability Index) — measures data distribution shift
    3. Semantic entropy — measures output reliability (hallucination detection)

    Each detector fails differently and independently. A model safe on PSI
    may hallucinate. A model hallucinating may have stable behavioural drift.
    Having three means a reviewer can see exactly what failed.

    The circuit breaker is the enforcement: when drift > threshold, the agent
    halts and the halt is logged as evidence (to Module 1 ledger).

    Thresholds:
    - Deterministic stub: always 0.15 (for demo, consistent but meaningless)
    - PSI: 0.25 (RBI standard for significant shift)
    - Semantic entropy: 0.30 (high entropy = high confabulation risk)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from datetime import datetime


class DriftType(str, Enum):
    """Type of drift detected."""

    DETERMINISTIC_STUB = "deterministic_stub"
    """Stub scorer — reproducible but does not measure real drift."""

    PSI_DATA = "psi_data"
    """Population Stability Index — input distribution shift."""

    SEMANTIC_ENTROPY = "semantic_entropy"
    """Semantic entropy — output confabulation/hallucination."""

    BEHAVIOURAL = "behavioural"
    """Decision distribution shift in the ledger."""


@dataclass(frozen=True)
class DriftScore:
    """A drift score from one detector."""

    detector_type: DriftType
    score: float
    threshold: float
    triggered: bool
    computed_at: datetime
    details: Optional[str] = None

    def __post_init__(self):
        """Validate score is in [0, 1]."""
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Score must be in [0, 1], got {self.score}")
        if not (0.0 <= self.threshold <= 1.0):
            raise ValueError(f"Threshold must be in [0, 1], got {self.threshold}")

    @property
    def margin(self) -> float:
        """
        Margin to threshold: how close to tripping.

        Positive margin = safe (score < threshold).
        Negative margin = triggered (score >= threshold).
        """
        return self.threshold - self.score


@dataclass(frozen=True)
class CircuitBreakerState:
    """State of the circuit breaker."""

    is_open: bool
    """True if the breaker is tripped (agent is halted)."""

    triggered_by: Optional[DriftScore] = None
    """The drift score that triggered the breaker (if open)."""

    halted_at: Optional[datetime] = None
    """When the breaker was tripped."""

    reason: Optional[str] = None
    """Human-readable reason (detector type and score)."""

    @classmethod
    def closed(cls) -> "CircuitBreakerState":
        """Circuit is closed (agent can proceed)."""
        return cls(is_open=False)

    @classmethod
    def open(
        cls,
        drift_score: DriftScore,
    ) -> "CircuitBreakerState":
        """
        Circuit is open (agent is halted).

        Args:
            drift_score: The drift score that triggered the breaker.

        Returns:
            New CircuitBreakerState with is_open=True.
        """
        return cls(
            is_open=True,
            triggered_by=drift_score,
            halted_at=datetime.utcnow(),
            reason=f"{drift_score.detector_type.value}: {drift_score.score:.3f} (threshold: {drift_score.threshold:.3f})",
        )


def compute_deterministic_drift_score(
    event_id: int,
    threshold: float = 0.15,
) -> DriftScore:
    """
    Compute a deterministic (stub) drift score.

    Always returns a score based on event_id, so it is reproducible but
    measures nothing real. Used for demonstration until real detectors ship.

    Args:
        event_id: Event identifier (used to seed the score).
        threshold: Drift threshold (default 0.15 for demo).

    Returns:
        DriftScore with deterministic but meaningless value.

    Note:
        This is a STUB. See LIMITATIONS.md for the production approach.
    """
    # Deterministic hash-based score (not real detection)
    score = abs((event_id * 17) % 100) / 100.0  # 0–1, deterministic
    triggered = score >= threshold

    return DriftScore(
        detector_type=DriftType.DETERMINISTIC_STUB,
        score=score,
        threshold=threshold,
        triggered=triggered,
        computed_at=datetime.utcnow(),
        details="Stub scorer: reproducible but does not measure real drift",
    )


def evaluate_circuit_breaker(
    drift_scores: List[DriftScore],
) -> CircuitBreakerState:
    """
    Evaluate the circuit breaker based on drift scores.

    If any detector triggers (score >= threshold), open the breaker.

    Args:
        drift_scores: List of DriftScore objects from all detectors.

    Returns:
        CircuitBreakerState: open if any detector triggered, closed otherwise.

    Example:
        >>> scores = [
        ...     DriftScore(DriftType.PSI_DATA, 0.10, 0.25, False, datetime.utcnow()),
        ...     DriftScore(DriftType.SEMANTIC_ENTROPY, 0.85, 0.30, True, datetime.utcnow()),
        ... ]
        >>> breaker = evaluate_circuit_breaker(scores)
        >>> breaker.is_open
        True  # Semantic entropy triggered
    """
    # Check if any detector triggered
    for score in drift_scores:
        if score.triggered:
            return CircuitBreakerState.open(score)

    # All clear
    return CircuitBreakerState.closed()


@dataclass(frozen=True)
class DriftReport:
    """
    Complete drift report: all scores + breaker state.

    Logged as evidence (to Module 1 ledger) when the breaker trips.
    """

    scores: List[DriftScore]
    breaker_state: CircuitBreakerState
    reported_at: datetime

    @classmethod
    def from_scores(cls, scores: List[DriftScore]) -> "DriftReport":
        """
        Create a drift report from detector scores.

        Args:
            scores: List of DriftScore objects.

        Returns:
            DriftReport with breaker state evaluated.
        """
        breaker = evaluate_circuit_breaker(scores)
        return cls(
            scores=scores,
            breaker_state=breaker,
            reported_at=datetime.utcnow(),
        )

    def summary(self) -> str:
        """
        Human-readable summary of the report.

        Returns:
            str: Multi-line summary of all scores and breaker status.
        """
        lines = ["Drift Report", "=" * 40]

        for score in self.scores:
            lines.append(
                f"{score.detector_type.value:20} | "
                f"score: {score.score:.3f} | "
                f"threshold: {score.threshold:.3f} | "
                f"triggered: {score.triggered}"
            )

        lines.append("-" * 40)
        if self.breaker_state.is_open:
            lines.append(f"🔴 BREAKER OPEN: {self.breaker_state.reason}")
        else:
            lines.append("🟢 BREAKER CLOSED: All detectors nominal")

        return "\n".join(lines)
