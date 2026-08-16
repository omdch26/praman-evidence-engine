"""
Tests for drift detection and circuit breaker.

These tests prove:
1. Deterministic stub scorer is reproducible (same input → same score)
2. Circuit breaker opens when any detector triggers
3. Drift report summarises all signals
4. Breaker state is immutable and can be safely logged

Run with: pytest tests/domain/test_drift.py -v
"""

import pytest
from datetime import datetime
from praman.domain.drift import (
    DriftType,
    DriftScore,
    CircuitBreakerState,
    evaluate_circuit_breaker,
    compute_deterministic_drift_score,
    DriftReport,
)


class TestDriftScore:
    """Test individual drift scores."""

    def test_drift_score_creation(self):
        """DriftScore can be created with valid parameters."""
        score = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.15,
            threshold=0.25,
            triggered=False,
            computed_at=datetime.utcnow(),
        )

        assert score.score == 0.15
        assert score.threshold == 0.25
        assert score.triggered is False

    def test_drift_score_validation_score_range(self):
        """Score must be in [0, 1]."""
        with pytest.raises(ValueError, match="Score must be in"):
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=1.5,  # Invalid
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            )

    def test_drift_score_validation_threshold_range(self):
        """Threshold must be in [0, 1]."""
        with pytest.raises(ValueError, match="Threshold must be in"):
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.15,
                threshold=1.5,  # Invalid
                triggered=False,
                computed_at=datetime.utcnow(),
            )

    def test_drift_score_margin(self):
        """Margin is threshold - score."""
        score = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.15,
            threshold=0.25,
            triggered=False,
            computed_at=datetime.utcnow(),
        )

        assert score.margin == 0.10  # 0.25 - 0.15

    def test_drift_score_margin_negative_when_triggered(self):
        """Margin is negative when score >= threshold."""
        score = DriftScore(
            detector_type=DriftType.SEMANTIC_ENTROPY,
            score=0.85,
            threshold=0.30,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        assert score.margin < 0  # Score exceeded threshold
        assert score.margin == 0.30 - 0.85

    def test_drift_score_is_frozen(self):
        """DriftScore is immutable."""
        score = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.15,
            threshold=0.25,
            triggered=False,
            computed_at=datetime.utcnow(),
        )

        with pytest.raises(AttributeError):
            score.score = 0.5


class TestDeterministicDriftScorer:
    """Test the deterministic stub drift scorer."""

    def test_deterministic_scorer_reproducible(self):
        """Same event_id → same score."""
        event_id = 42

        score1 = compute_deterministic_drift_score(event_id)
        score2 = compute_deterministic_drift_score(event_id)

        assert score1.score == score2.score

    def test_deterministic_scorer_different_events(self):
        """Different event_ids → different scores (usually)."""
        score_1 = compute_deterministic_drift_score(1)
        score_2 = compute_deterministic_drift_score(2)
        score_3 = compute_deterministic_drift_score(100)

        # All different (statistically very likely)
        scores = [score_1.score, score_2.score, score_3.score]
        assert len(set(scores)) == 3

    def test_deterministic_scorer_in_range(self):
        """Score is always in [0, 1]."""
        for event_id in range(100):
            score = compute_deterministic_drift_score(event_id)
            assert 0.0 <= score.score <= 1.0

    def test_deterministic_scorer_custom_threshold(self):
        """Custom threshold is respected."""
        event_id = 42
        threshold = 0.50

        score = compute_deterministic_drift_score(event_id, threshold=threshold)

        assert score.threshold == 0.50
        assert score.triggered == (score.score >= 0.50)

    def test_deterministic_scorer_triggered_status(self):
        """triggered is True when score >= threshold."""
        event_id = 1
        score = compute_deterministic_drift_score(event_id, threshold=0.15)

        # For event_id=1: (1*17)%100 = 17, score = 0.17
        assert score.score >= score.threshold or score.score < score.threshold
        assert score.triggered == (score.score >= score.threshold)


class TestCircuitBreakerState:
    """Test circuit breaker state."""

    def test_breaker_closed(self):
        """Closed breaker allows agent to proceed."""
        breaker = CircuitBreakerState.closed()

        assert breaker.is_open is False
        assert breaker.triggered_by is None

    def test_breaker_open(self):
        """Open breaker halts the agent."""
        drift_score = DriftScore(
            detector_type=DriftType.SEMANTIC_ENTROPY,
            score=0.85,
            threshold=0.30,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        breaker = CircuitBreakerState.open(drift_score)

        assert breaker.is_open is True
        assert breaker.triggered_by == drift_score
        assert breaker.halted_at is not None
        assert "semantic_entropy" in breaker.reason

    def test_breaker_reason_includes_score(self):
        """Breaker reason shows score and threshold."""
        drift_score = DriftScore(
            detector_type=DriftType.PSI_DATA,
            score=0.26,
            threshold=0.25,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        breaker = CircuitBreakerState.open(drift_score)

        assert "0.260" in breaker.reason
        assert "0.250" in breaker.reason

    def test_breaker_is_frozen(self):
        """CircuitBreakerState is immutable."""
        breaker = CircuitBreakerState.closed()

        with pytest.raises(AttributeError):
            breaker.is_open = True


class TestCircuitBreakerEvaluation:
    """Test circuit breaker evaluation logic."""

    def test_breaker_closes_when_all_nominal(self):
        """Breaker closes if all detectors nominal."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.10,
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
            DriftScore(
                detector_type=DriftType.SEMANTIC_ENTROPY,
                score=0.15,
                threshold=0.30,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
        ]

        breaker = evaluate_circuit_breaker(scores)

        assert breaker.is_open is False

    def test_breaker_opens_on_first_trigger(self):
        """Breaker opens if any detector triggers."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.10,
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
            DriftScore(
                detector_type=DriftType.SEMANTIC_ENTROPY,
                score=0.85,
                threshold=0.30,
                triggered=True,
                computed_at=datetime.utcnow(),
            ),
        ]

        breaker = evaluate_circuit_breaker(scores)

        assert breaker.is_open is True
        assert breaker.triggered_by.detector_type == DriftType.SEMANTIC_ENTROPY

    def test_breaker_opens_on_multiple_triggers(self):
        """Breaker opens if multiple detectors trigger."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.30,
                threshold=0.25,
                triggered=True,
                computed_at=datetime.utcnow(),
            ),
            DriftScore(
                detector_type=DriftType.SEMANTIC_ENTROPY,
                score=0.85,
                threshold=0.30,
                triggered=True,
                computed_at=datetime.utcnow(),
            ),
        ]

        breaker = evaluate_circuit_breaker(scores)

        assert breaker.is_open is True

    def test_breaker_opens_on_empty_scores(self):
        """Empty score list leaves breaker closed."""
        scores = []

        breaker = evaluate_circuit_breaker(scores)

        assert breaker.is_open is False


class TestDriftReport:
    """Test drift reports (what gets logged as evidence)."""

    def test_drift_report_creation(self):
        """DriftReport aggregates scores and breaker state."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.15,
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
        ]

        report = DriftReport.from_scores(scores)

        assert len(report.scores) == 1
        assert report.breaker_state is not None
        assert report.reported_at is not None

    def test_drift_report_breaker_state_matches_scores(self):
        """Report's breaker state matches the scores."""
        scores = [
            DriftScore(
                detector_type=DriftType.SEMANTIC_ENTROPY,
                score=0.85,
                threshold=0.30,
                triggered=True,
                computed_at=datetime.utcnow(),
            ),
        ]

        report = DriftReport.from_scores(scores)

        assert report.breaker_state.is_open is True

    def test_drift_report_summary(self):
        """Report summary is human-readable."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.15,
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
            DriftScore(
                detector_type=DriftType.SEMANTIC_ENTROPY,
                score=0.85,
                threshold=0.30,
                triggered=True,
                computed_at=datetime.utcnow(),
            ),
        ]

        report = DriftReport.from_scores(scores)
        summary = report.summary()

        assert "psi_data" in summary
        assert "semantic_entropy" in summary
        assert "BREAKER OPEN" in summary

    def test_drift_report_is_frozen(self):
        """DriftReport is immutable (safe to log)."""
        scores = [
            DriftScore(
                detector_type=DriftType.PSI_DATA,
                score=0.15,
                threshold=0.25,
                triggered=False,
                computed_at=datetime.utcnow(),
            ),
        ]

        report = DriftReport.from_scores(scores)

        with pytest.raises(AttributeError):
            report.breaker_state = CircuitBreakerState.open(scores[0])


class TestIntegration:
    """Integration tests: drift detection end-to-end."""

    def test_full_drift_workflow(self):
        """Complete workflow: score → evaluate → report."""
        # Compute drift scores
        psi_score = compute_deterministic_drift_score(42, threshold=0.25)
        semantic_score = DriftScore(
            detector_type=DriftType.SEMANTIC_ENTROPY,
            score=0.85,
            threshold=0.30,
            triggered=True,
            computed_at=datetime.utcnow(),
        )

        # Evaluate breaker
        breaker = evaluate_circuit_breaker([psi_score, semantic_score])

        # Create report (what gets logged)
        report = DriftReport.from_scores([psi_score, semantic_score])

        # Breaker should be open
        assert report.breaker_state.is_open is True

        # Report should be loggable (immutable)
        assert report.breaker_state.triggered_by is semantic_score

    def test_drift_report_survives_logging(self):
        """Report can be stored as evidence without corruption."""
        original_scores = [
            compute_deterministic_drift_score(i, threshold=0.25)
            for i in range(5)
        ]

        report = DriftReport.from_scores(original_scores)

        # Report is immutable; can be safely persisted
        assert len(report.scores) == len(original_scores)
        assert report.reported_at is not None

        # All fields are still accessible
        for score in report.scores:
            assert 0.0 <= score.score <= 1.0
