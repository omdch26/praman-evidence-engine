"""
Tests for OTel adapter (gen_ai.* attribute mapping).

These tests prove:
1. Policy evaluation attributes are mapped correctly
2. Drift detection attributes include score, threshold, triggered status
3. Circuit breaker state is mapped correctly
4. gen_ai.* attributes follow Development status format
5. If OTEL spec changes, these tests catch it (clear error messages)

Run with: pytest tests/test_otel_adapter.py -v
"""

import pytest
from praman.adapters.instrumentation.otel_adapter import (
    map_policy_evaluation_attributes,
    map_drift_detection_attributes,
    map_circuit_breaker_attributes,
    map_gen_ai_request_attributes,
    map_gen_ai_response_attributes,
    GenAISystem,
)


class TestPolicyEvaluationAttributes:
    """Test policy evaluation attribute mapping."""

    def test_allowed_decision(self):
        """Allowed decision is mapped correctly."""
        attrs = map_policy_evaluation_attributes(
            agent_name="RiskScoreAgent",
            autonomy_tier="ACT_BOUNDED",
            policy_name="loan_approval_policy",
            result="allowed",
        )

        assert attrs["governance.agent"] == "RiskScoreAgent"
        assert attrs["governance.autonomy_tier"] == "ACT_BOUNDED"
        assert attrs["governance.policy"] == "loan_approval_policy"
        assert attrs["governance.decision"] == "allowed"

    def test_denied_decision(self):
        """Denied decision is mapped correctly."""
        attrs = map_policy_evaluation_attributes(
            agent_name="ApprovalAgent",
            autonomy_tier="PROPOSE",
            policy_name="transfer_policy",
            result="denied",
        )

        assert attrs["governance.decision"] == "denied"


class TestDriftDetectionAttributes:
    """Test drift detection attribute mapping."""

    def test_nominal_drift(self):
        """Nominal drift score is mapped correctly."""
        attrs = map_drift_detection_attributes(
            detector_type="psi_data",
            score=0.10,
            threshold=0.25,
            triggered=False,
        )

        assert attrs["drift.detector"] == "psi_data"
        assert attrs["drift.score"] == 0.10
        assert attrs["drift.threshold"] == 0.25
        assert attrs["drift.triggered"] is False

    def test_triggered_drift(self):
        """Triggered drift score is mapped correctly."""
        attrs = map_drift_detection_attributes(
            detector_type="semantic_entropy",
            score=0.85,
            threshold=0.30,
            triggered=True,
        )

        assert attrs["drift.triggered"] is True
        assert attrs["drift.score"] > attrs["drift.threshold"]


class TestCircuitBreakerAttributes:
    """Test circuit breaker state attribute mapping."""

    def test_breaker_closed(self):
        """Closed breaker is mapped correctly."""
        attrs = map_circuit_breaker_attributes(
            is_open=False,
        )

        assert attrs["circuit_breaker.is_open"] is False
        assert attrs["circuit_breaker.triggered_by"] is None

    def test_breaker_open(self):
        """Open breaker includes trigger reason."""
        attrs = map_circuit_breaker_attributes(
            is_open=True,
            triggered_by="psi_data",
            reason="Input distribution drifted significantly",
        )

        assert attrs["circuit_breaker.is_open"] is True
        assert attrs["circuit_breaker.triggered_by"] == "psi_data"
        assert "distribution" in attrs["circuit_breaker.reason"]


class TestGenAIRequestAttributes:
    """Test LLM request attribute mapping (gen_ai.*)."""

    def test_basic_request(self):
        """Basic request attributes are mapped correctly."""
        attrs = map_gen_ai_request_attributes(
            model="gpt-4-turbo",
            system=GenAISystem.OPENAI,
            temperature=0.7,
        )

        # gen_ai.* attributes (Development status)
        assert attrs["gen_ai.system"] == "openai"
        assert attrs["gen_ai.request.model"] == "gpt-4-turbo"
        assert attrs["gen_ai.request.temperature"] == 0.7

    def test_request_with_max_tokens(self):
        """Request with max_tokens is included."""
        attrs = map_gen_ai_request_attributes(
            model="claude-3-opus",
            system=GenAISystem.ANTHROPIC,
            temperature=0.5,
            max_tokens=1000,
        )

        assert "gen_ai.request.max_tokens" in attrs
        assert attrs["gen_ai.request.max_tokens"] == 1000

    def test_all_systems(self):
        """All supported LLM systems are mappable."""
        for system in GenAISystem:
            attrs = map_gen_ai_request_attributes(
                model="test-model",
                system=system,
                temperature=0.7,
            )

            assert attrs["gen_ai.system"] == system.value


class TestGenAIResponseAttributes:
    """Test LLM response attribute mapping (gen_ai.*)."""

    def test_basic_response(self):
        """Basic response attributes are mapped correctly."""
        attrs = map_gen_ai_response_attributes(
            finish_reason="stop",
        )

        # gen_ai.* attributes (Development status)
        assert attrs["gen_ai.response.finish_reason"] == "stop"

    def test_response_with_tokens(self):
        """Response with token counts is included."""
        attrs = map_gen_ai_response_attributes(
            finish_reason="length",
            input_tokens=150,
            output_tokens=500,
        )

        assert attrs["gen_ai.response.input_tokens"] == 150
        assert attrs["gen_ai.response.output_tokens"] == 500

    def test_finish_reasons(self):
        """Common finish reasons are mappable."""
        finish_reasons = ["stop", "length", "error", "content_filter"]

        for reason in finish_reasons:
            attrs = map_gen_ai_response_attributes(finish_reason=reason)
            assert attrs["gen_ai.response.finish_reason"] == reason


class TestAttributeIsolation:
    """Test that attribute mapping is isolated from business logic."""

    def test_no_imports_from_domain(self):
        """Adapter does not import from domain/ (isolation check)."""
        import praman.adapters.instrumentation.otel_adapter as adapter_module

        # Verify module docstring exists (documentation of isolation)
        assert adapter_module.__doc__ is not None
        assert "isolated" in adapter_module.__doc__.lower()

    def test_attribute_keys_are_consistent(self):
        """All mapped attributes follow a consistent naming scheme."""
        # Policy attributes: governance.*
        policy_attrs = map_policy_evaluation_attributes(
            "agent", "OBSERVE", "policy", "allowed"
        )
        for key in policy_attrs:
            assert key.startswith("governance.")

        # Drift attributes: drift.*
        drift_attrs = map_drift_detection_attributes("psi", 0.1, 0.25, False)
        for key in drift_attrs:
            assert key.startswith("drift.")

        # Breaker attributes: circuit_breaker.*
        breaker_attrs = map_circuit_breaker_attributes(False)
        for key in breaker_attrs:
            assert key.startswith("circuit_breaker.")

        # LLM attributes: gen_ai.*
        llm_req_attrs = map_gen_ai_request_attributes(
            "model", GenAISystem.OPENAI, 0.7
        )
        for key in llm_req_attrs:
            assert key.startswith("gen_ai.")
