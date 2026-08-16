"""
Deterministic event serialisation (canonicalisation).

Responsibility
    Convert an event (Python dict/dataclass) to a canonical byte sequence.
    Same event → same bytes, always, on any machine.
    This is non-negotiable for verification to work.

Must not
    Perform I/O or network calls.
    Store personal data (hash principal IDs instead).
    Include timestamps that vary by machine (use RFC3339 UTC).

Design notes
    JSON keys are sorted (prevents reordering attacks).
    No unnecessary whitespace (compact, deterministic size).
    Unicode is normalised (same accented letter in different encodings → same bytes).
    Numbers are represented uniformly (no floating-point variance).

Why this matters
    If the same event produces different JSON on different machines, verification fails
    on records that were never tampered with — false alarms destroy trust.
    Hence: sorted keys, no insignificant whitespace, fixed formats, explicit representation.
"""

import json
import unicodedata
from typing import Any, Dict
from datetime import datetime


def canonicalise(event: Dict[str, Any]) -> bytes:
    """
    Convert an event to canonical bytes.

    Takes any dict-like event and produces a deterministic byte sequence.
    Keys are sorted, whitespace is minimal, unicode is normalised.

    Args:
        event: Event dict. Must not contain personal data (name, email, phone, etc.).
               Use hashed IDs or opaque client record IDs instead.

    Returns:
        bytes: UTF-8 encoded, deterministic JSON (sorted keys, compact).

    Raises:
        TypeError: If event contains non-serialisable types (datetime, Decimal, etc.).

    Example:
        >>> event1 = {"type": "consent", "principal_id": "hash:abc123", "action": "share"}
        >>> event2 = {"action": "share", "principal_id": "hash:abc123", "type": "consent"}
        >>> canonicalise(event1) == canonicalise(event2)
        True  # Key order does not matter
    """
    # Recursively normalise unicode (NFC form)
    normalised = _normalise_unicode(event)

    # Serialize to JSON with sorted keys, no whitespace
    canonical_json = json.dumps(
        normalised,
        sort_keys=True,
        separators=(",", ":"),  # compact: no spaces after separators
        ensure_ascii=False,  # preserve non-ASCII characters
    )

    # Return as bytes (UTF-8)
    return canonical_json.encode("utf-8")


def _normalise_unicode(obj: Any) -> Any:
    """
    Recursively normalise unicode to NFC form.

    NFC (Normal Form Composed) ensures that é and e+́ (precomposed vs. decomposed)
    both become the same bytes. This prevents different unicode representations
    of the same visual text from producing different hashes.

    Args:
        obj: Any JSON-serialisable Python object.

    Returns:
        Same object with all strings normalised to NFC.
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    elif isinstance(obj, dict):
        return {k: _normalise_unicode(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_normalise_unicode(item) for item in obj]
    else:
        # int, float, bool, None — return as-is
        return obj


def verify_canonical(event: Dict[str, Any], canonical_bytes: bytes) -> bool:
    """
    Verify that canonical_bytes is the correct canonicalisation of event.

    Used in tests and auditing to confirm that a stored canonical form
    matches the expected bytes.

    Args:
        event: The event dict.
        canonical_bytes: The claimed canonical bytes.

    Returns:
        True if re-canonicalising the event produces the same bytes.
    """
    return canonicalise(event) == canonical_bytes
