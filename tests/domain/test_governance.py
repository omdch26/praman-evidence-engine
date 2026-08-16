"""
Tests for agent governance — autonomy tiers and delegation ceilings.

These tests prove:
1. Tiers form a lattice (partial order)
2. Privilege cannot escalate through delegation (ceiling enforcement)
3. Tier comparisons work correctly
4. Tier capabilities are monotonic (higher tier ⊇ lower tier)

The core test: test_delegation_cannot_escalate_privilege. This proves the
distinctive multi-agent security property: malicious agents cannot escalate
by spawning children.

Run with: pytest tests/domain/test_governance.py -v
"""

import pytest
from praman.domain.governance import (
    AutonomyTier,
    DelegationCeiling,
    apply_delegation_ceiling,
    can_escalate_privilege,
)


class TestAutonomyTierEnum:
    """Test the AutonomyTier enumeration and ordering."""

    def test_tiers_exist(self):
        """All four autonomy tiers are defined."""
        assert AutonomyTier.OBSERVE is not None
        assert AutonomyTier.PROPOSE is not None
        assert AutonomyTier.ACT_BOUNDED is not None
        assert AutonomyTier.ACT_FULL is not None

    def test_tier_ordering_forms_lattice(self):
        """Tiers form a lattice: OBSERVE < PROPOSE < ACT_BOUNDED < ACT_FULL."""
        assert AutonomyTier.OBSERVE < AutonomyTier.PROPOSE
        assert AutonomyTier.PROPOSE < AutonomyTier.ACT_BOUNDED
        assert AutonomyTier.ACT_BOUNDED < AutonomyTier.ACT_FULL

        # Transitivity
        assert AutonomyTier.OBSERVE < AutonomyTier.ACT_FULL

    def test_tier_equality(self):
        """Tiers can be compared for equality."""
        tier1 = AutonomyTier.ACT_BOUNDED
        tier2 = AutonomyTier.ACT_BOUNDED

        assert tier1 == tier2
        assert not (tier1 < tier2)
        assert tier1 <= tier2

    def test_tier_not_equal_to_other_types(self):
        """Comparing tier to a non-numeric type returns False, not an error."""
        tier = AutonomyTier.OBSERVE

        # AutonomyTier is an IntEnum, so it equals its int value by design
        # (OBSERVE == 0). It is not, however, equal to unrelated types.
        assert not (tier == "OBSERVE")
        assert tier == 0

    def test_tier_permits_capability(self):
        """permits() checks if a tier allows a capability."""
        # ACT_FULL permits all capabilities
        assert AutonomyTier.ACT_FULL.permits(AutonomyTier.OBSERVE)
        assert AutonomyTier.ACT_FULL.permits(AutonomyTier.PROPOSE)
        assert AutonomyTier.ACT_FULL.permits(AutonomyTier.ACT_BOUNDED)
        assert AutonomyTier.ACT_FULL.permits(AutonomyTier.ACT_FULL)

        # OBSERVE permits only OBSERVE
        assert AutonomyTier.OBSERVE.permits(AutonomyTier.OBSERVE)
        assert not AutonomyTier.OBSERVE.permits(AutonomyTier.PROPOSE)
        assert not AutonomyTier.OBSERVE.permits(AutonomyTier.ACT_BOUNDED)

        # PROPOSE permits OBSERVE and PROPOSE
        assert AutonomyTier.PROPOSE.permits(AutonomyTier.OBSERVE)
        assert AutonomyTier.PROPOSE.permits(AutonomyTier.PROPOSE)
        assert not AutonomyTier.PROPOSE.permits(AutonomyTier.ACT_BOUNDED)


class TestDelegationCeiling:
    """Test delegation ceiling enforcement."""

    def test_ceiling_effective_tier_no_escalation(self):
        """Child cannot escalate beyond parent's tier."""
        parent = AutonomyTier.PROPOSE
        declared = AutonomyTier.ACT_FULL

        ceiling = DelegationCeiling(parent, declared)

        # Child declared ACT_FULL but is capped at parent's PROPOSE
        assert ceiling.effective_tier == AutonomyTier.PROPOSE

    def test_ceiling_effective_tier_child_lower(self):
        """Child can declare a lower tier than parent."""
        parent = AutonomyTier.ACT_FULL
        declared = AutonomyTier.PROPOSE

        ceiling = DelegationCeiling(parent, declared)

        # Child can stay at lower tier
        assert ceiling.effective_tier == AutonomyTier.PROPOSE

    def test_ceiling_effective_tier_both_same(self):
        """Child can match parent's tier."""
        parent = AutonomyTier.ACT_BOUNDED
        declared = AutonomyTier.ACT_BOUNDED

        ceiling = DelegationCeiling(parent, declared)

        assert ceiling.effective_tier == AutonomyTier.ACT_BOUNDED

    def test_ceiling_is_minimum(self):
        """Effective tier is always min(parent, declared)."""
        for parent in [AutonomyTier.OBSERVE, AutonomyTier.PROPOSE,
                       AutonomyTier.ACT_BOUNDED, AutonomyTier.ACT_FULL]:
            for declared in [AutonomyTier.OBSERVE, AutonomyTier.PROPOSE,
                            AutonomyTier.ACT_BOUNDED, AutonomyTier.ACT_FULL]:
                ceiling = DelegationCeiling(parent, declared)
                expected = AutonomyTier(min(int(parent), int(declared)))
                assert ceiling.effective_tier == expected

    def test_ceiling_validation(self):
        """validate() returns True for properly formed ceilings."""
        ceiling = DelegationCeiling(AutonomyTier.PROPOSE, AutonomyTier.ACT_BOUNDED)

        assert ceiling.validate() is True

    def test_ceiling_is_frozen(self):
        """DelegationCeiling is immutable."""
        ceiling = DelegationCeiling(AutonomyTier.OBSERVE, AutonomyTier.PROPOSE)

        with pytest.raises(AttributeError):
            ceiling.parent_tier = AutonomyTier.ACT_FULL


class TestDelegationCeilingFunction:
    """Test the apply_delegation_ceiling function."""

    def test_apply_ceiling_no_escalation(self):
        """Applying ceiling prevents privilege escalation."""
        parent = AutonomyTier.ACT_BOUNDED
        declared = AutonomyTier.ACT_FULL

        effective = apply_delegation_ceiling(parent, declared)

        assert effective == AutonomyTier.ACT_BOUNDED

    def test_apply_ceiling_all_combinations(self):
        """apply_delegation_ceiling works for all tier combinations."""
        for parent in [AutonomyTier.OBSERVE, AutonomyTier.PROPOSE,
                      AutonomyTier.ACT_BOUNDED, AutonomyTier.ACT_FULL]:
            for declared in [AutonomyTier.OBSERVE, AutonomyTier.PROPOSE,
                            AutonomyTier.ACT_BOUNDED, AutonomyTier.ACT_FULL]:
                effective = apply_delegation_ceiling(parent, declared)
                expected = AutonomyTier(min(int(parent), int(declared)))
                assert effective == expected


class TestPrivilegeEscalation:
    """Test detection of privilege escalation attempts."""

    def test_can_escalate_true(self):
        """can_escalate_privilege returns True when child > parent."""
        parent = AutonomyTier.PROPOSE
        declared = AutonomyTier.ACT_FULL

        assert can_escalate_privilege(parent, declared) is True

    def test_can_escalate_false_lower(self):
        """can_escalate_privilege returns False when child < parent."""
        parent = AutonomyTier.ACT_FULL
        declared = AutonomyTier.OBSERVE

        assert can_escalate_privilege(parent, declared) is False

    def test_can_escalate_false_equal(self):
        """can_escalate_privilege returns False when child == parent."""
        parent = AutonomyTier.ACT_BOUNDED
        declared = AutonomyTier.ACT_BOUNDED

        assert can_escalate_privilege(parent, declared) is False

    def test_escalation_attempts_are_blocked(self):
        """
        Even if a child tries to escalate, ceiling enforcement blocks it.

        This is the core security property: attempted escalation is detected
        and mitigated.
        """
        parent = AutonomyTier.OBSERVE
        declared = AutonomyTier.ACT_FULL

        # Yes, child tried to escalate
        assert can_escalate_privilege(parent, declared) is True

        # But the ceiling stops it
        effective = apply_delegation_ceiling(parent, declared)
        assert effective == AutonomyTier.OBSERVE


class TestMultiLevelDelegation:
    """Test privilege escalation across multiple levels."""

    def test_escalation_blocked_at_each_level(self):
        """
        Escalation is blocked at each delegation step, not just between parent and child.

        A → B → C chain:
        - A has PROPOSE
        - B tries to declare ACT_FULL (escalation attempt)
        - B's effective is min(PROPOSE, ACT_FULL) = PROPOSE
        - C tries to declare ACT_FULL (escalation attempt via B)
        - C's effective is min(PROPOSE, ACT_FULL) = PROPOSE
        """
        tier_a = AutonomyTier.PROPOSE

        # B tries to escalate from A
        tier_b_declared = AutonomyTier.ACT_FULL
        tier_b_effective = apply_delegation_ceiling(tier_a, tier_b_declared)
        assert tier_b_effective == AutonomyTier.PROPOSE

        # C tries to escalate from B
        tier_c_declared = AutonomyTier.ACT_FULL
        tier_c_effective = apply_delegation_ceiling(tier_b_effective, tier_c_declared)
        assert tier_c_effective == AutonomyTier.PROPOSE

        # C cannot escalate no matter how many levels deep

    def test_privilege_trickles_down(self):
        """Privilege limitation trickles down the delegation chain."""
        tier_a = AutonomyTier.ACT_BOUNDED
        tier_b = apply_delegation_ceiling(tier_a, AutonomyTier.ACT_FULL)
        tier_c = apply_delegation_ceiling(tier_b, AutonomyTier.ACT_FULL)

        # Each level is capped at or below the previous
        assert tier_b <= tier_a
        assert tier_c <= tier_b
        assert tier_c <= tier_a


class TestGovernanceIntegration:
    """Integration tests: governance tiers in realistic scenarios."""

    def test_loan_application_chain(self):
        """
        Realistic scenario: three-agent loan decision chain.

        1. GatheringAgent (OBSERVE) — reads credit bureau
        2. RiskScoreAgent (ACT_BOUNDED) — computes risk; limited to write decisions
        3. ApprovalAgent (PROPOSE) — drafts approval; human commits
        """
        # GatheringAgent runs at OBSERVE
        gathering_tier = AutonomyTier.OBSERVE
        assert gathering_tier.permits(AutonomyTier.OBSERVE)
        assert not gathering_tier.permits(AutonomyTier.ACT_BOUNDED)

        # If GatheringAgent tries to spawn RiskScoreAgent at ACT_FULL
        risk_declared = AutonomyTier.ACT_FULL
        risk_effective = apply_delegation_ceiling(gathering_tier, risk_declared)
        # Risk is capped at gathering's tier
        assert risk_effective == AutonomyTier.OBSERVE

        # ApprovalAgent at parent's PROPOSE level
        approval_tier = AutonomyTier.PROPOSE
        approval_effective = apply_delegation_ceiling(risk_effective, approval_tier)
        # Approval is capped at min(OBSERVE, PROPOSE) = OBSERVE
        assert approval_effective == AutonomyTier.OBSERVE

    def test_escalation_attempt_in_chain(self):
        """
        Malicious scenario: an agent tries to escalate through child spawning.

        Even if an agent is compromised and tries to spawn a high-privilege child,
        the ceiling prevents it.
        """
        compromised_tier = AutonomyTier.ACT_BOUNDED
        malicious_declared = AutonomyTier.ACT_FULL

        # Malicious agent tries to spawn at ACT_FULL
        effective = apply_delegation_ceiling(compromised_tier, malicious_declared)

        # Ceiling blocks it
        assert effective == AutonomyTier.ACT_BOUNDED
        assert effective < malicious_declared
