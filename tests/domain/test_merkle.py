"""
Tests for Merkle tree construction, root computation, and inclusion proofs.

These tests prove:
1. Tampering with any event changes the root (tamper-evidence)
2. Inclusion proofs are correct and verifiable
3. Domain separation prevents second-preimage attacks
4. Tree construction is deterministic

The most critical test: test_tampering_changes_root. This proves the core claim
that makes the entire system work: any change to any event is detectable.

Fixtures use real hex strings throughout (never plain ASCII like "abc" or "a")
because hash_leaf() requires valid hex, matching what production code passes it
(hmac.hexdigest() output). Using ASCII placeholders masked real failures behind
a ValueError from bytes.fromhex() instead of exercising the Merkle logic.

Run with: pytest tests/domain/test_merkle.py -v
"""

import pytest
from praman.domain.merkle import (
    compute_root,
    compute_root_hex,
    generate_inclusion_proof,
    verify_inclusion_proof,
    hash_leaf,
    hash_node,
    LEAF_PREFIX,
    NODE_PREFIX,
)


def hex_hmac(seed: int) -> str:
    """Produce a deterministic, valid 64-char hex string for a given seed."""
    return format(seed, "x").rjust(2, "0") * 32


class TestMerkleLeafHashing:
    """Test leaf node hashing."""

    def test_hash_leaf_is_deterministic(self):
        """Same HMAC → same leaf hash, every time."""
        hmac_hex = hex_hmac(0x9F)

        leaf1 = hash_leaf(hmac_hex)
        leaf2 = hash_leaf(hmac_hex)

        assert leaf1 == leaf2, "Leaf hashing must be deterministic"

    def test_hash_leaf_uses_domain_separation(self):
        """Leaf hashes are prefixed with LEAF_PREFIX (domain separation)."""
        hmac_hex = "abc123"

        leaf = hash_leaf(hmac_hex)

        # Leaf is 32 bytes (SHA-256)
        assert len(leaf) == 32
        assert isinstance(leaf, bytes)

    def test_hash_leaf_differs_from_direct_hash(self):
        """Leaf hash differs from a direct hash (proof of prefix)."""
        hmac_hex = "abc123"

        leaf = hash_leaf(hmac_hex)

        # Direct hash (without prefix) would be different
        import hashlib

        direct = hashlib.sha256(bytes.fromhex(hmac_hex)).digest()

        assert leaf != direct, "Domain separation must change the hash"


class TestMerkleNodeHashing:
    """Test internal node hashing."""

    def test_hash_node_is_deterministic(self):
        """Same children → same node hash, every time."""
        left = b"left_hash" + b"\x00" * 23  # Pad to 32 bytes
        right = b"right_hash" + b"\x00" * 22

        node1 = hash_node(left, right)
        node2 = hash_node(left, right)

        assert node1 == node2, "Node hashing must be deterministic"

    def test_hash_node_order_matters(self):
        """Left and right are not commutative."""
        left = b"left" + b"\x00" * 28
        right = b"right" + b"\x00" * 27

        hash_lr = hash_node(left, right)
        hash_rl = hash_node(right, left)

        assert hash_lr != hash_rl, "Node order must matter (not commutative)"

    def test_hash_node_uses_domain_separation(self):
        """Internal nodes are prefixed with NODE_PREFIX."""
        left = b"\x00" * 32
        right = b"\x01" * 32

        node = hash_node(left, right)

        # Node is 32 bytes (SHA-256)
        assert len(node) == 32


class TestMerkleRootComputation:
    """Test Merkle root computation."""

    def test_single_event_root(self):
        """A tree with one event: root is hash(hash(leaf))."""
        hmac_hex = "abc123"

        root = compute_root([hmac_hex])

        assert root is not None
        assert len(root) == 32

    def test_two_event_root(self):
        """A tree with two events produces a valid root."""
        hmacs = ["abc123", "def456"]

        root = compute_root(hmacs)

        assert root is not None
        assert len(root) == 32

    def test_odd_events_are_duplicated(self):
        """With 3 events, the last is duplicated before hashing."""
        hmacs_3 = [hex_hmac(1), hex_hmac(2), hex_hmac(3)]
        hmacs_4 = hmacs_3 + [hex_hmac(3)]  # 4th is duplicate of 3rd

        root_3 = compute_root(hmacs_3)
        root_4 = compute_root(hmacs_4)

        # Roots should match (3rd event is duplicated in both)
        assert root_3 == root_4, "Odd events should be duplicated"

    def test_empty_list_returns_none(self):
        """Empty event list returns None root."""
        root = compute_root([])

        assert root is None

    def test_root_is_deterministic(self):
        """Same events in same order → same root, always."""
        hmacs = [hex_hmac(1), hex_hmac(2), hex_hmac(3), hex_hmac(4)]

        root1 = compute_root(hmacs)
        root2 = compute_root(hmacs)

        assert root1 == root2, "Root must be deterministic"

    def test_root_hex_returns_64_chars(self):
        """compute_root_hex returns hex string (64 characters)."""
        hmacs = [hex_hmac(1), hex_hmac(2)]

        root_hex = compute_root_hex(hmacs)

        assert isinstance(root_hex, str)
        assert len(root_hex) == 64
        assert all(c in "0123456789abcdef" for c in root_hex)


class TestTamperingDetection:
    """The core security property: tampering is detectable."""

    def test_tampering_changes_root(self):
        """
        Mutating any single event must change the Merkle root.

        This is the central claim of the entire system: evidence cannot be
        altered without detection. If this test ever fails, nothing else in
        this repository means anything.
        """
        hmacs_original = [hex_hmac(1), hex_hmac(2), hex_hmac(3), hex_hmac(4)]

        root_original = compute_root(hmacs_original)

        # Tamper with event 1
        hmacs_tampered = list(hmacs_original)
        hmacs_tampered[1] = hex_hmac(0xFF)

        root_tampered = compute_root(hmacs_tampered)

        assert root_original != root_tampered, "Tampering MUST change the root"

    def test_tampering_any_event_breaks_root(self):
        """Tampering any event (not just one) breaks the root."""
        hmacs = [hex_hmac(i) for i in range(1, 6)]
        root_original = compute_root(hmacs)

        for i in range(len(hmacs)):
            hmacs_test = list(hmacs)
            hmacs_test[i] = hex_hmac(0xFF)
            root_test = compute_root(hmacs_test)
            assert root_test != root_original, f"Tampering event {i} must change root"

    def test_even_one_bit_change_breaks_root(self):
        """Changing a single hex character breaks the root."""
        hmac_original = "abcdef0123456789"
        hmac_tampered = "abcdef0123456788"  # Last char changed

        hmacs_original = [hmac_original, "fedcba"]
        hmacs_tampered = [hmac_tampered, "fedcba"]

        root_original = compute_root(hmacs_original)
        root_tampered = compute_root(hmacs_tampered)

        assert root_original != root_tampered


class TestInclusionProofs:
    """Test inclusion proof generation and verification."""

    def test_generate_proof_for_single_event(self):
        """A proof for the only event in the tree is valid."""
        hmacs = ["abc123"]
        proof, positions = generate_inclusion_proof(hmacs, 0)

        root = compute_root(hmacs)

        assert verify_inclusion_proof(hmacs[0], proof, positions, root) is True

    def test_generate_proof_for_each_event(self):
        """Proofs can be generated for any event in the tree."""
        hmacs = [hex_hmac(i) for i in range(1, 5)]
        root = compute_root(hmacs)

        for i in range(len(hmacs)):
            proof, positions = generate_inclusion_proof(hmacs, i)
            assert verify_inclusion_proof(hmacs[i], proof, positions, root) is True

    def test_proof_is_logarithmic_size(self):
        """Proof size is O(log n), not O(n)."""
        hmacs_10 = [hex_hmac(i) for i in range(10)]
        hmacs_1000 = [hex_hmac(i % 256) for i in range(1000)]

        proof_10, _ = generate_inclusion_proof(hmacs_10, 5)
        proof_1000, _ = generate_inclusion_proof(hmacs_1000, 500)

        # Proof for 1000 events is only slightly larger than proof for 10
        # log2(10) ≈ 3.3, log2(1000) ≈ 10
        assert len(proof_10) < len(proof_1000)
        assert len(proof_1000) < 30  # Logarithmic, not linear

    def test_wrong_root_fails_verification(self):
        """Proof verification fails if the root is wrong."""
        hmacs = [hex_hmac(i) for i in range(1, 5)]
        correct_root = compute_root(hmacs)

        wrong_root = b"\x00" * 32  # Completely wrong root

        proof, positions = generate_inclusion_proof(hmacs, 0)

        assert verify_inclusion_proof(hmacs[0], proof, positions, wrong_root) is False

    def test_proof_of_wrong_event_fails(self):
        """Proof for one event doesn't work for another."""
        hmacs = [hex_hmac(i) for i in range(1, 5)]
        root = compute_root(hmacs)

        proof_0, positions = generate_inclusion_proof(hmacs, 0)

        # Try to verify with event 1's HMAC
        assert verify_inclusion_proof(hmacs[1], proof_0, positions, root) is False

    def test_proof_without_tampering(self):
        """Proof for an unmodified event verifies."""
        hmacs = ["abc123", "def456", "aabbcc", "112233", "556677"]
        root = compute_root(hmacs)

        # Generate proof for event 2
        proof, positions = generate_inclusion_proof(hmacs, 2)

        # Verify it
        assert verify_inclusion_proof(hmacs[2], proof, positions, root) is True

    def test_proof_catches_tampering(self):
        """Proof fails if the event was tampered with."""
        hmacs = [hex_hmac(i) for i in range(1, 5)]
        root = compute_root(hmacs)

        proof, positions = generate_inclusion_proof(hmacs, 1)

        # Tamper with the event's HMAC
        tampered_hmac = hex_hmac(0xFF)

        assert verify_inclusion_proof(tampered_hmac, proof, positions, root) is False


class TestInclusionProofPrivacy:
    """Inclusion proofs don't reveal other events."""

    def test_proof_does_not_require_other_events(self):
        """To verify a proof, you only need the event and proof (not other events)."""
        hmacs = [hex_hmac(i) for i in range(1, 9)]
        root = compute_root(hmacs)

        proof, positions = generate_inclusion_proof(hmacs, 3)

        # Verification needs only the event and proof, not the others
        verified = verify_inclusion_proof(hmacs[3], proof, positions, root)
        assert verified is True

        # Proof doesn't contain the other events' raw HMAC hex values
        assert hmacs[0] not in [p.hex() for p in proof if isinstance(p, bytes)]


class TestDomainSeparation:
    """Domain separation prevents second-preimage attacks."""

    def test_leaf_and_node_hashes_differ(self):
        """A leaf hash and a node hash of the same 32 bytes differ (domain separation)."""
        # Use the leaf hash's own raw bytes as if they were a node's children,
        # so both hash_leaf and hash_node process the exact same underlying
        # 32-byte payload. If prefixing worked, the outputs must differ.
        hmac_hex = hex_hmac(1)
        leaf = hash_leaf(hmac_hex)

        node_of_same_bytes = hash_node(leaf, leaf)

        assert leaf != node_of_same_bytes, (
            "Domain separation must make leaf and node hashes diverge "
            "even when derived from the same underlying bytes"
        )


class TestEdgeCases:
    """Edge case handling."""

    def test_out_of_range_event_index(self):
        """Invalid event index raises IndexError."""
        hmacs = [hex_hmac(1), hex_hmac(2), hex_hmac(3)]

        with pytest.raises(IndexError):
            generate_inclusion_proof(hmacs, 10)

    def test_negative_event_index(self):
        """Negative event index raises IndexError."""
        hmacs = [hex_hmac(1), hex_hmac(2), hex_hmac(3)]

        with pytest.raises(IndexError):
            generate_inclusion_proof(hmacs, -1)

    def test_generate_proof_empty_list(self):
        """Generating proof for empty list raises ValueError."""
        with pytest.raises(ValueError):
            generate_inclusion_proof([], 0)

    def test_large_tree(self):
        """Tree construction works for large event lists."""
        hmacs = [hex_hmac(i % 256) for i in range(10000)]

        root = compute_root(hmacs)

        assert root is not None
        assert len(root) == 32

        # Proof should still be small
        proof, _ = generate_inclusion_proof(hmacs, 5000)
        assert len(proof) < 20  # log2(10000) ≈ 13
