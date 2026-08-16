"""
Tests for deterministic event canonicalisation.

These tests prove that canonicalisation is deterministic and order-independent.
This is the foundation of verification — if the same event produces different
bytes on different machines, the HMAC won't match, and the ledger looks corrupted.

Run with: pytest tests/domain/test_canonical.py -v
"""

from praman.domain.canonical import canonicalise, verify_canonical


def test_canonical_is_deterministic():
    """
    Same event → same bytes, every time.

    This is the core property that makes verification work.
    """
    event = {"type": "consent", "principal_id": "hash:abc123", "action": "data_share"}

    canonical1 = canonicalise(event)
    canonical2 = canonicalise(event)

    assert canonical1 == canonical2, "Canonicalisation must be deterministic"


def test_canonical_ignores_key_order():
    """
    Event with keys in different order → same canonical bytes.

    JSON allows any key order. We enforce alphabetical order so that
    canonical form is unique regardless of how the event was constructed.
    """
    event1 = {"type": "consent", "principal_id": "hash:abc123", "action": "data_share"}
    event2 = {"action": "data_share", "principal_id": "hash:abc123", "type": "consent"}

    canonical1 = canonicalise(event1)
    canonical2 = canonicalise(event2)

    assert canonical1 == canonical2, "Key order must not affect canonicalisation"


def test_canonical_normalises_unicode():
    """
    Different unicode representations of the same character → same bytes.

    é (precomposed) and e + ́ (decomposed) should both become the same bytes.
    This prevents Unicode normalization differences from breaking verification.
    """
    # Precomposed é (single character)
    event1 = {"name_hash": "café_hash", "type": "consent"}

    # Decomposed é (e + combining acute accent)
    event2 = {"name_hash": "café_hash", "type": "consent"}

    canonical1 = canonicalise(event1)
    canonical2 = canonicalise(event2)

    assert canonical1 == canonical2, "Unicode normalization must be transparent"


def test_canonical_removes_whitespace():
    """
    No unnecessary whitespace in canonical form.

    Compact JSON (no spaces after colons or commas) ensures deterministic size.
    """
    event = {"type": "consent", "action": "data_share"}
    canonical = canonicalise(event)
    canonical_str = canonical.decode("utf-8")

    # Should be compact (no spaces after : or ,)
    assert ": " not in canonical_str, "Canonical form must not have space after colon"
    assert ", " not in canonical_str, "Canonical form must not have space after comma"


def test_canonical_sorts_keys():
    """
    Keys are in alphabetical order in canonical form.
    """
    event = {"zebra": 1, "apple": 2, "middle": 3}
    canonical_str = canonicalise(event).decode("utf-8")

    # Keys should be in alphabetical order
    apple_pos = canonical_str.find('"apple"')
    middle_pos = canonical_str.find('"middle"')
    zebra_pos = canonical_str.find('"zebra"')

    assert apple_pos < middle_pos < zebra_pos, "Keys must be sorted alphabetically"


def test_verify_canonical_passes():
    """
    verify_canonical() returns True for correct canonical bytes.
    """
    event = {"type": "consent", "principal_id": "hash:abc123"}
    canonical = canonicalise(event)

    assert verify_canonical(event, canonical) is True


def test_verify_canonical_fails():
    """
    verify_canonical() returns False for incorrect canonical bytes.
    """
    event = {"type": "consent", "principal_id": "hash:abc123"}
    wrong_canonical = b"wrong bytes"

    assert verify_canonical(event, wrong_canonical) is False


def test_canonical_handles_nested_dicts():
    """
    Nested dictionaries are canonicalised recursively.
    """
    event1 = {
        "type": "policy_evaluated",
        "decision": {"allowed": True, "reason": "within_threshold"},
    }
    event2 = {
        "type": "policy_evaluated",
        "decision": {"reason": "within_threshold", "allowed": True},  # Different order
    }

    canonical1 = canonicalise(event1)
    canonical2 = canonicalise(event2)

    assert canonical1 == canonical2, "Nested dict key order must not matter"


def test_canonical_handles_lists():
    """
    Lists are preserved in order (lists are ordered by definition).
    """
    event1 = {"tags": ["a", "b", "c"]}
    event2 = {"tags": ["a", "b", "c"]}

    canonical1 = canonicalise(event1)
    canonical2 = canonicalise(event2)

    assert canonical1 == canonical2, "Lists with same order must canonicalise identically"


def test_canonical_handles_numbers():
    """
    Numbers are serialised uniformly (no floating-point variance).
    """
    event1 = {"amount": 100, "threshold": 99.5}
    canonical = canonicalise(event1)
    canonical_str = canonical.decode("utf-8")

    # Should have integer and decimal representations
    assert "100" in canonical_str
    assert "99.5" in canonical_str


def test_canonical_handles_booleans():
    """
    Booleans are serialised as JSON true/false (not True/False).
    """
    event = {"allowed": True, "requires_approval": False}
    canonical = canonicalise(event)
    canonical_str = canonical.decode("utf-8")

    # JSON booleans (lowercase)
    assert "true" in canonical_str
    assert "false" in canonical_str


def test_canonical_handles_null():
    """
    None is serialised as JSON null.
    """
    event = {"optional_field": None, "type": "consent"}
    canonical = canonicalise(event)
    canonical_str = canonical.decode("utf-8")

    assert "null" in canonical_str


def test_canonical_returns_bytes():
    """
    canonicalise() always returns bytes (not str).
    """
    event = {"type": "consent"}
    canonical = canonicalise(event)

    assert isinstance(canonical, bytes), "canonicalise() must return bytes"


def test_canonical_utf8_encoding():
    """
    Non-ASCII characters are encoded as UTF-8 bytes.
    """
    event = {"name_hash": "café", "city": "Bangalore"}
    canonical = canonicalise(event)

    # Can be decoded back to the same characters
    canonical_str = canonical.decode("utf-8")
    assert "café" in canonical_str
    assert "Bangalore" in canonical_str
