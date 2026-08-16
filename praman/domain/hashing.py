"""
HMAC-SHA256 computation and chaining for event integrity.

Responsibility
    Compute HMAC of canonical events to prove authenticity and integrity.
    Chain HMACs so that altering any event breaks the chain visibly.

Must not
    Perform I/O or network calls.
    Store the client key (caller provides it; Praman does not hold it).
    Know anything about the event beyond its canonical bytes.

Design notes
    Each event's HMAC depends on:
    1. The canonical bytes of the event
    2. The tenant's HMAC key (client-held, not vendor-held)
    3. The previous event's HMAC (chaining)

    Altering any event breaks the chain and all subsequent HMACs.
    Chaining enforces ordering integrity — not just "this event is unaltered"
    but "this event occupies this position in this sequence".

    Why client-held key:
    - Vendor cannot forge records (lacks the key)
    - In a dispute, the client can state: "the vendor could not have fabricated this"
    - The vendor's incentive to lie becomes irrelevant, because they lack capability
"""

import hmac
import hashlib
from typing import Optional
from praman.domain.canonical import canonicalise


def compute_hmac(
    canonical_bytes: bytes,
    hmac_key: bytes,
    previous_hmac: Optional[bytes] = None,
) -> bytes:
    """
    Compute HMAC-SHA256 of canonical bytes, with optional chaining.

    The HMAC includes:
    1. The canonical bytes of the event
    2. The previous event's HMAC (if provided), creating a chain

    Args:
        canonical_bytes: Deterministic JSON bytes (from canonicalise()).
        hmac_key: Client-held HMAC key (256-bit, base64-decoded, as bytes).
        previous_hmac: The HMAC of the previous event (for chaining).
                       If None, this is the first event (chain starts here).

    Returns:
        bytes: The computed HMAC-SHA256 (32 bytes / 64 hex characters).

    Example:
        >>> key = b"\\x00" * 32  # 256 bits of zeros (for testing only)
        >>> event1_canonical = b'{"type":"consent"}'
        >>> hmac1 = compute_hmac(event1_canonical, key)
        >>> event2_canonical = b'{"type":"consent_withdraw"}'
        >>> hmac2 = compute_hmac(event2_canonical, key, previous_hmac=hmac1)
        >>> hmac1 != hmac2  # Different HMACs
        >>> # If event1 is altered, hmac1 changes, which breaks hmac2
    """
    # Construct the message to be HMACed
    if previous_hmac is not None:
        # Chain: include previous HMAC in the message
        message = previous_hmac + canonical_bytes
    else:
        # First event: no chaining
        message = canonical_bytes

    # Compute HMAC-SHA256
    h = hmac.new(hmac_key, message, hashlib.sha256)
    return h.digest()  # 32 bytes


def compute_hmac_hex(
    canonical_bytes: bytes,
    hmac_key: bytes,
    previous_hmac_hex: Optional[str] = None,
) -> str:
    """
    Compute HMAC-SHA256 and return as hexadecimal string.

    Convenience wrapper for compute_hmac() that works with hex-encoded previous HMACs
    (as they are typically stored in databases).

    Args:
        canonical_bytes: Deterministic JSON bytes.
        hmac_key: Client-held HMAC key (bytes).
        previous_hmac_hex: Previous event's HMAC as hex string (64 chars).

    Returns:
        str: The computed HMAC as hex string (64 characters).

    Example:
        >>> key = b"\\x00" * 32
        >>> event1_canonical = b'{"type":"consent"}'
        >>> hmac1_hex = compute_hmac_hex(event1_canonical, key)
        >>> len(hmac1_hex)
        64  # 32 bytes × 2 hex chars per byte
    """
    # Decode previous HMAC from hex (if provided)
    previous_hmac = None
    if previous_hmac_hex is not None:
        previous_hmac = bytes.fromhex(previous_hmac_hex)

    # Compute HMAC
    h = compute_hmac(canonical_bytes, hmac_key, previous_hmac)

    # Return as hex
    return h.hex()


def verify_hmac_chain(
    events: list[tuple[bytes, bytes]],  # [(canonical_bytes, expected_hmac_hex), ...]
    hmac_key: bytes,
) -> bool:
    """
    Verify the entire HMAC chain.

    Checks that each event's HMAC matches the expected value given the key and
    the previous event's HMAC.

    Args:
        events: List of (canonical_bytes, expected_hmac_hex) tuples.
        hmac_key: Client-held HMAC key (bytes).

    Returns:
        True if the entire chain is valid (all HMACs match).

    Example:
        >>> key = b"\\x00" * 32
        >>> event1 = b'{"type":"consent"}'
        >>> hmac1 = compute_hmac_hex(event1, key)
        >>> event2 = b'{"type":"consent_withdraw"}'
        >>> hmac2 = compute_hmac_hex(event2, key, previous_hmac_hex=hmac1)
        >>> events = [(event1, hmac1), (event2, hmac2)]
        >>> verify_hmac_chain(events, key)
        True
    """
    previous_hmac_hex = None

    for canonical_bytes, expected_hmac_hex in events:
        computed_hmac_hex = compute_hmac_hex(canonical_bytes, hmac_key, previous_hmac_hex)

        # Compare
        if computed_hmac_hex != expected_hmac_hex:
            return False

        # Move to next event
        previous_hmac_hex = computed_hmac_hex

    return True


def validate_hmac_key(hmac_key: bytes) -> None:
    """
    Validate that the HMAC key meets minimum security requirements.

    Args:
        hmac_key: The key to validate (should be bytes).

    Raises:
        ValueError: If the key is too short (less than 32 bytes / 256 bits).
        TypeError: If the key is not bytes.

    Example:
        >>> validate_hmac_key(b"\\x00" * 32)  # OK: 256 bits
        >>> validate_hmac_key(b"short")  # Raises ValueError
    """
    if not isinstance(hmac_key, bytes):
        raise TypeError(f"HMAC key must be bytes, not {type(hmac_key).__name__}")

    if len(hmac_key) < 32:
        raise ValueError(
            f"HMAC key must be at least 32 bytes (256 bits). Got {len(hmac_key)} bytes."
        )
