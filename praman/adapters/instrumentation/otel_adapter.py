"""
OpenTelemetry attribute mapping (gen_ai.* Development status).

Responsibility
    Map Praman domain concepts to OTel gen_ai.* attribute format.
    Centralise attribute naming (if spec changes, only this file changes).
    Provide utilities for emitting domain-specific traces.

Must not
    Import from domain/, services/, or api/.
    Contain business logic.
    Emit traces directly (call from observability/ or services/).

Design notes
    gen_ai.* attributes are in Development status (June 2026).
    This adapter isolates the mapping so that if OTEL evolves,
    only this file needs to change. Tests will catch breaking changes.

    Example: If gen_ai.request.model → gen_ai.model in future,
    change the constant here and update test_otel_adapter.py.

See also
    docs/ADR/0013-otel-genai-conventions.md
    praman/observability/otel.py
"""

from typing import Dict, Any, Optional
from enum import Enum


class GenAISystem(str, Enum):
    """Supported LLM providers (gen_ai.system)."""

    OPENAI = "openai"
    AZURE = "azure"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


def map_policy_evaluation_attributes(
    agent_name: str,
    autonomy_tier: str,
    policy_name: str,
    result: str,  # "allowed" | "denied"
) -> Dict[str, Any]:
    """
    Map a policy evaluation to OTel span attributes.

    Args:
        agent_name: Name of the agent being evaluated
        autonomy_tier: Tier of the agent (OBSERVE, PROPOSE, etc.)
        policy_name: Policy that was evaluated
        result: "allowed" or "denied"

    Returns:
        Dict of OTel span attributes
    """
    return {
        "governance.agent": agent_name,
        "governance.autonomy_tier": autonomy_tier,
        "governance.policy": policy_name,
        "governance.decision": result,
    }


def map_drift_detection_attributes(
    detector_type: str,
    score: float,
    threshold: float,
    triggered: bool,
) -> Dict[str, Any]:
    """
    Map a drift detection result to OTel span attributes.

    Args:
        detector_type: Type of detector (psi_data, semantic_entropy, etc.)
        score: Computed drift score (0–1)
        threshold: Trigger threshold (0–1)
        triggered: Whether the detector triggered

    Returns:
        Dict of OTel span attributes
    """
    return {
        "drift.detector": detector_type,
        "drift.score": score,
        "drift.threshold": threshold,
        "drift.triggered": triggered,
    }


def map_circuit_breaker_attributes(
    is_open: bool,
    triggered_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map circuit breaker state to OTel span attributes.

    Args:
        is_open: Whether the breaker is open (halted)
        triggered_by: Detector that triggered (if open)
        reason: Human-readable reason for state

    Returns:
        Dict of OTel span attributes
    """
    return {
        "circuit_breaker.is_open": is_open,
        "circuit_breaker.triggered_by": triggered_by,
        "circuit_breaker.reason": reason,
    }


def map_gen_ai_request_attributes(
    model: str,
    system: GenAISystem,
    temperature: float,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Map LLM request details to OTel gen_ai.* attributes.

    Note: gen_ai.* attributes are Development status (June 2026).
    If spec changes, update this function only.

    Args:
        model: Model identifier (e.g., "gpt-4-turbo")
        system: LLM provider (openai, azure, ollama, etc.)
        temperature: Sampling temperature (0–1)
        max_tokens: Maximum tokens to generate (optional)

    Returns:
        Dict of OTel span attributes with gen_ai.* prefix
    """
    attrs = {
        "gen_ai.system": system.value,
        "gen_ai.request.model": model,
        "gen_ai.request.temperature": temperature,
    }

    if max_tokens is not None:
        attrs["gen_ai.request.max_tokens"] = max_tokens

    return attrs


def map_gen_ai_response_attributes(
    finish_reason: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Map LLM response details to OTel gen_ai.* attributes.

    Args:
        finish_reason: Why generation stopped (stop, length, error, etc.)
        input_tokens: Number of input tokens (optional)
        output_tokens: Number of output tokens (optional)

    Returns:
        Dict of OTel span attributes with gen_ai.* prefix
    """
    attrs = {
        "gen_ai.response.finish_reason": finish_reason,
    }

    if input_tokens is not None:
        attrs["gen_ai.response.input_tokens"] = input_tokens

    if output_tokens is not None:
        attrs["gen_ai.response.output_tokens"] = output_tokens

    return attrs
