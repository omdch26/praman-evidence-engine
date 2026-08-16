"""
Agent governance kernel — autonomy tiers and delegation ceilings.

Responsibility
    Define autonomy tiers as a lattice (not a hierarchy).
    Enforce delegation ceilings: child's effective tier = min(parent, declared).
    Prevent privilege escalation through agent spawning (the distinctive multi-agent attack).

Must not
    Perform I/O or network calls.
    Know about the database or ledger (operates on pure tier logic).
    Make policy decisions (that is the PolicyEngine's job).

Design notes
    Tiers form a partial order: OBSERVE ⊆ PROPOSE ⊆ ACT_BOUNDED ⊆ ACT_FULL
    (each tier permits all previous tier's operations plus new ones).

    When Agent A (tier=2) spawns Agent B (declared=3), B's effective tier is
    min(2, 3) = 2. This is non-negotiable: privilege cannot escalate through
    delegation, because A cannot grant what A does not have.

    The lattice property is load-bearing: it means you can prove that a
    malicious agent cannot escalate by spawning a child and declaring it
    higher authority. This is the core of the multi-agent security story.

    Tool authorisation and parameter limits are separate concerns (belong to
    services/ and adapters/), but tiers enforce a tier-based default: OBSERVE
    has no tools, PROPOSE has read-only tools, etc.
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, Set
from functools import total_ordering


@total_ordering
class AutonomyTier(IntEnum):
    """
    Autonomy tier as a lattice (partial order).

    Each tier permits all operations of lower tiers plus additional capabilities.
    This forms a lattice where comparisons are meaningful: tier X < tier Y means
    "agent at X has a subset of agent Y's permissions".

    Lower numeric value = more restricted.
    """

    OBSERVE = 0
    """
    Agent may read only. No side effects.

    Examples: query a credit bureau, read a customer record, analyse historical data.
    Tool calls that modify state (write, delete, call external APIs with side effects)
    are rejected.
    """

    PROPOSE = 1
    """
    Agent may draft actions. Human must commit them.

    Output is never executed directly. It is routed to a HITL (human-in-the-loop)
    queue. A human reviews and approves or rejects. The agent cannot observe
    whether its proposal was accepted — it just proposes.

    Architecturally non-bypassable: the kernel routes PROPOSE output to HITL,
    not to downstream tools.
    """

    ACT_BOUNDED = 2
    """
    Agent may execute within a declared allowlist and value caps.

    Tool calls must be in the agent's allowed-tools list.
    Numeric parameters (loan amount, transfer size, rate) must be within caps.
    A tool call outside the allowlist or exceeding a limit is refused and logged.

    Examples: agent with tools=["credit_bureau.read", "decision.write"] and
    limits={"loan_amount_inr": 500_000} can read credit data and write
    decisions, but cannot transfer money or query a different bureau.
    """

    ACT_FULL = 3
    """
    Agent may execute freely within policy constraints.

    Requires an explicit tenant policy. No tool allowlist. No value cap enforced
    by the tier itself (but policies may impose them). This tier is for
    high-trust agents in low-risk operations.

    Still enforced: policies and drift detection. The difference is tool-level
    authorisation is not enforced; the agent trusts its own judgement.
    """

    def __lt__(self, other):
        """Support comparison: OBSERVE < PROPOSE < ACT_BOUNDED < ACT_FULL."""
        if not isinstance(other, AutonomyTier):
            return NotImplemented
        return int(self) < int(other)

    def __eq__(self, other):
        """Support equality."""
        if not isinstance(other, AutonomyTier):
            return NotImplemented
        return int(self) == int(other)

    def permits(self, capability: "AutonomyTier") -> bool:
        """
        Check if this tier permits a capability.

        A tier permits a capability if the capability's tier is less than or equal.

        Args:
            capability: The tier level of the capability being checked.

        Returns:
            bool: True if this tier permits the capability.

        Example:
            >>> AutonomyTier.ACT_BOUNDED.permits(AutonomyTier.OBSERVE)
            True  # ACT_BOUNDED can do what OBSERVE can
            >>> AutonomyTier.OBSERVE.permits(AutonomyTier.PROPOSE)
            False  # OBSERVE cannot do what PROPOSE can
        """
        return int(self) >= int(capability)


@dataclass(frozen=True)
class DelegationCeiling:
    """
    Ceiling on privilege when an agent spawns a child.

    When Agent A (parent_tier) spawns Agent B (declared_tier), B's effective
    tier is min(parent_tier, declared_tier). This is the delegation ceiling:
    a child cannot exceed its parent's privilege, no matter what it declares.
    """

    parent_tier: AutonomyTier
    declared_tier: AutonomyTier

    @property
    def effective_tier(self) -> AutonomyTier:
        """
        Compute the effective tier for a spawned agent.

        Returns:
            AutonomyTier: min(parent_tier, declared_tier)

        Example:
            >>> parent = AutonomyTier.ACT_BOUNDED
            >>> declared = AutonomyTier.ACT_FULL
            >>> ceiling = DelegationCeiling(parent, declared)
            >>> ceiling.effective_tier
            <AutonomyTier.ACT_BOUNDED: 2>
        """
        return AutonomyTier(min(int(self.parent_tier), int(self.declared_tier)))

    def validate(self) -> bool:
        """
        Validate that the ceiling is properly formed (both tiers are valid).

        This is a sanity check; in practice, AutonomyTier enums are always valid.

        Returns:
            bool: Always True for properly constructed DelegationCeiling.
        """
        return (
            isinstance(self.parent_tier, AutonomyTier)
            and isinstance(self.declared_tier, AutonomyTier)
        )


def apply_delegation_ceiling(
    parent_tier: AutonomyTier,
    declared_tier: AutonomyTier,
) -> AutonomyTier:
    """
    Apply a delegation ceiling: compute effective tier for a spawned agent.

    Args:
        parent_tier: The parent agent's autonomy tier.
        declared_tier: The child agent's declared tier.

    Returns:
        AutonomyTier: The child's effective tier = min(parent, declared).

    Example:
        >>> parent = AutonomyTier.PROPOSE
        >>> declared = AutonomyTier.ACT_FULL
        >>> effective = apply_delegation_ceiling(parent, declared)
        >>> effective == AutonomyTier.PROPOSE
        True  # Child cannot escalate beyond parent's tier
    """
    ceiling = DelegationCeiling(parent_tier, declared_tier)
    return ceiling.effective_tier


def can_escalate_privilege(
    parent_tier: AutonomyTier,
    declared_tier: AutonomyTier,
) -> bool:
    """
    Check if a child agent could escalate privilege through spawning.

    Returns:
        bool: True if declared_tier > parent_tier (would violate ceiling if not enforced).

    This is a diagnostic function — use apply_delegation_ceiling() to enforce it.

    Example:
        >>> can_escalate_privilege(AutonomyTier.ACT_BOUNDED, AutonomyTier.ACT_FULL)
        True  # Child tried to escalate
        >>> can_escalate_privilege(AutonomyTier.ACT_FULL, AutonomyTier.OBSERVE)
        False  # Child is not escalating
    """
    return int(declared_tier) > int(parent_tier)
