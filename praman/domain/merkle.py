"""
Merkle tree construction, root computation, and inclusion proofs.

Responsibility
    Build a binary Merkle tree over event HMACs.
    Prove any event change is detectable (root changes).
    Generate and verify inclusion proofs (prove one event is in the tree without revealing others).

Must not
    Perform I/O or network calls.
    Know about the ledger or database (operates on a list of HMACs).
    Fail silently on inconsistency (raise exceptions).

Design notes
    Odd nodes are duplicated (the CT convention). This is known to enable a
    second-preimage class of attack (Bitcoin CVE-2012-2459) unless leaf and
    internal nodes are domain-separated. We prefix leaves with 0x00 and
    internal nodes with 0x01 for exactly that reason.

    Trees are rebuilt per window (per anchor) rather than maintained
    incrementally. Windows are bounded, so O(n) on a small n and the
    simplicity is worth more than saved cycles. Revisit with MMR if
    anchoring frequency increases.

    Inclusion proofs allow proving one event is in the tree without
    disclosing the others — commercially valuable (regulator asks about one
    customer's consent; you prove that event without disclosing others).
"""

import hashlib
from typing import List, Tuple, Optional


# Domain separation prefixes (prevent second-preimage attack)
LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def hash_leaf(hmac_hex: str) -> bytes:
    """
    Hash a leaf node (an event's HMAC).

    Args:
        hmac_hex: HMAC value as hex string (64 characters).

    Returns:
        bytes: SHA-256 hash of the leaf (32 bytes).
    """
    # Prefix with LEAF_PREFIX for domain separation
    hmac_bytes = bytes.fromhex(hmac_hex)
    data = LEAF_PREFIX + hmac_bytes
    return hashlib.sha256(data).digest()


def hash_node(left: bytes, right: bytes) -> bytes:
    """
    Hash an internal node (combination of two subtrees).

    Args:
        left: Left child hash (32 bytes).
        right: Right child hash (32 bytes).

    Returns:
        bytes: SHA-256 hash of the node (32 bytes).
    """
    # Prefix with NODE_PREFIX for domain separation
    data = NODE_PREFIX + left + right
    return hashlib.sha256(data).digest()


def compute_root(hmac_hex_list: List[str]) -> bytes:
    """
    Compute the Merkle root over a list of event HMACs.

    If the list has an odd number of elements, the last element is
    duplicated before hashing (standard CT convention).

    Args:
        hmac_hex_list: List of HMAC values (as hex strings). Empty list returns None.

    Returns:
        bytes: The Merkle root (32 bytes), or None if list is empty.

    Example:
        >>> hmacs = ["9f86d081...", "abc123...", "def456..."]
        >>> root = compute_root(hmacs)
        >>> len(root)
        32  # 256 bits
    """
    if not hmac_hex_list:
        return None

    # Convert HMACs to leaf hashes
    leaves = [hash_leaf(hmac_hex) for hmac_hex in hmac_hex_list]

    # Build the tree bottom-up
    current_level = leaves

    while len(current_level) > 1:
        next_level = []

        # Process pairs
        for i in range(0, len(current_level), 2):
            left = current_level[i]

            # If odd, duplicate the last element
            right = current_level[i + 1] if i + 1 < len(current_level) else left

            # Hash the pair
            node = hash_node(left, right)
            next_level.append(node)

        current_level = next_level

    # Single node left: the root
    return current_level[0]


def compute_root_hex(hmac_hex_list: List[str]) -> Optional[str]:
    """
    Compute the Merkle root and return as hex string.

    Convenience wrapper for compute_root().

    Args:
        hmac_hex_list: List of HMAC hex strings.

    Returns:
        str: Root as hex string (64 characters), or None if list is empty.
    """
    root = compute_root(hmac_hex_list)
    return root.hex() if root else None


def generate_inclusion_proof(
    hmac_hex_list: List[str],
    event_index: int,
) -> Tuple[List[bytes], List[str]]:
    """
    Generate an inclusion proof for one event in the tree.

    The proof is a list of sibling hashes — the minimum information needed
    to recompute the root from a single leaf. The verifier computes:
    hash(leaf, proof[0]) → compute up the tree using proof[1], proof[2], ...

    Args:
        hmac_hex_list: List of HMAC hex strings in the tree.
        event_index: Index of the event to prove (0-based).

    Returns:
        Tuple of:
        - proof: List of sibling hashes (bytes).
        - positions: List of "L" (left sibling) or "R" (right sibling) for each proof element.

    Raises:
        IndexError: If event_index is out of range.
        ValueError: If the list is empty.

    Example:
        >>> hmacs = ["abc", "def", "ghi", "jkl"]
        >>> proof, positions = generate_inclusion_proof(hmacs, 2)
        >>> # To verify: start with hash_leaf(hmacs[2])
        >>> # hash with proof[0] using position positions[0]
        >>> # Continue up the tree
    """
    if not hmac_hex_list:
        raise ValueError("Cannot generate proof for empty list")

    if event_index < 0 or event_index >= len(hmac_hex_list):
        raise IndexError(f"Event index {event_index} out of range [0, {len(hmac_hex_list) - 1}]")

    # Convert to leaf hashes
    leaves = [hash_leaf(hmac_hex) for hmac_hex in hmac_hex_list]

    proof = []
    positions = []

    # Walk the tree, collecting siblings
    current_level = leaves
    current_index = event_index

    while len(current_level) > 1:
        # Is our target on the left or right?
        is_left = current_index % 2 == 0

        if is_left:
            # Target is left; sibling is right
            sibling_index = current_index + 1
            if sibling_index < len(current_level):
                # Right sibling exists
                proof.append(current_level[sibling_index])
                positions.append("R")
            else:
                # No right sibling; use duplication (left duplicate)
                proof.append(current_level[current_index])
                positions.append("L_DUP")
        else:
            # Target is right; sibling is left
            sibling_index = current_index - 1
            proof.append(current_level[sibling_index])
            positions.append("L")

        # Move up
        current_level_next = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            node = hash_node(left, right)
            current_level_next.append(node)

        current_level = current_level_next
        current_index = current_index // 2

    return proof, positions


def verify_inclusion_proof(
    event_hmac_hex: str,
    proof: List[bytes],
    positions: List[str],
    root: bytes,
) -> bool:
    """
    Verify an inclusion proof.

    Recomputes the root from the event's HMAC and the proof, then
    compares to the claimed root.

    Args:
        event_hmac_hex: The event's HMAC (as hex string).
        proof: List of sibling hashes from generate_inclusion_proof().
        positions: List of "L", "R", or "L_DUP" from generate_inclusion_proof().
        root: The claimed Merkle root (bytes).

    Returns:
        bool: True if the proof is valid (recomputed root matches the claimed root).

    Example:
        >>> hmacs = ["abc", "def", "ghi", "jkl"]
        >>> root = compute_root(hmacs)
        >>> proof, positions = generate_inclusion_proof(hmacs, 2)
        >>> verify_inclusion_proof(hmacs[2], proof, positions, root)
        True
    """
    if len(proof) != len(positions):
        return False

    # Start with the leaf
    current = hash_leaf(event_hmac_hex)

    # Walk up the tree
    for sibling, position in zip(proof, positions):
        if position == "L":
            current = hash_node(sibling, current)
        elif position == "R":
            current = hash_node(current, sibling)
        elif position == "L_DUP":
            # Duplicated left sibling (odd node case)
            current = hash_node(sibling, current)
        else:
            return False

    # Check if we arrived at the root
    return current == root


def merkle_root_hex(hmac_hex_list: List[str]) -> Optional[str]:
    """
    Compute Merkle root as hex string (alias for compute_root_hex).
    """
    return compute_root_hex(hmac_hex_list)
