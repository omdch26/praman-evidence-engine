"""
Independent verification of an evidence bundle — pure, no I/O.

Responsibility
    Recompute a Merkle root from a bundle's canonical event data, verify
    an Ed25519 signature over that recomputed root, and verify HMAC chain
    continuity — all without touching the database, the network, or
    anything the server currently claims.

Must not
    Trust any precomputed value in the bundle as an input to verifying
    itself. Recomputing the root FROM the events, then checking the
    server's claimed root against OUR recomputed one, is the entire point
    — verifying the server's own number against the server's own
    signature proves nothing about tampering, only that the server can
    multiply.
    Perform I/O. This module is the domain-layer proof engine; fetching a
    bundle over HTTP is services/evidence_service.py's job, not this
    module's.

Design notes
    Every check function returns a structured pass/fail result rather than
    raising on failure. A verifier's job is to report what it found, not
    to stop at the first problem — a reviewer wants to know the chain
    broke at sequence 3 AND that the signature also failed, not just
    "something, somewhere, is wrong."

    This module is deliberately the one both the FastAPI-facing service
    (services/evidence_service.py) and the standalone offline verifier
    (scripts/verify_bundle.py) would conceptually share the *algorithm*
    with — though scripts/verify_bundle.py intentionally does NOT import
    from praman/ (see that file's docstring for why), so the algorithms
    are independently re-implemented there, not shared code. What is
    shared is the specification: this module's tests
    (test_independently_recomputed_root_matches_server_root, etc.) and
    the standalone verifier's tests both check the same worked example
    against the same expected output.
"""

from dataclasses import dataclass, field
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root


@dataclass(frozen=True)
class CheckResult:
    """One verification check's outcome."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerificationReport:
    """
    The full result of verifying an evidence bundle.

    Attributes:
        overall_passed: True only if every individual check passed.
        checks: Per-check breakdown, in the order the checks ran.
        first_divergent_sequence: If the HMAC chain or Merkle root check
            failed, the lowest event sequence number where recomputed and
            claimed values first differ. None if nothing diverged (or if
            the divergence could not be localised to one event, e.g. a
            root mismatch with a fully valid HMAC chain — see
            recompute_root_from_bundle's docstring for why that case
            cannot name a single sequence).
    """

    overall_passed: bool
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)
    first_divergent_sequence: Optional[int] = None


def verify_hmac_chain_continuity(
    events: list[dict],
    hmac_key: bytes,
) -> tuple[bool, Optional[int]]:
    """
    Recompute each event's HMAC from its canonical JSON and confirm it
    matches the bundle's claimed hmac_value, honouring the chain (each
    event's HMAC input includes the previous event's HMAC).

    Args:
        events: Bundle event dicts, each with "sequence", "canonical_json"
            (the exact bytes that were hashed, as a str), and "hmac_value".
            Must be in ascending sequence order.
        hmac_key: The key used to compute these HMACs. For this demo build
            this is the disclosed fixed stub key (see
            docs/LIMITATIONS.md) — a real per-tenant-key deployment would
            need the tenant's own key, which by design this module never
            holds.

    Returns:
        (True, None) if every event's HMAC matches, given the chain.
        (False, sequence) where sequence is the first event whose
        recomputed HMAC does not match its claimed value.
    """
    previous_hmac_hex: Optional[str] = None

    for event in events:
        canonical_bytes = event["canonical_json"].encode("utf-8")
        recomputed_hmac = compute_hmac_hex(canonical_bytes, hmac_key, previous_hmac_hex)

        if recomputed_hmac != event["hmac_value"]:
            return False, event["sequence"]

        previous_hmac_hex = event["hmac_value"]

    return True, None


def recompute_root_from_bundle(events: list[dict]) -> bytes:
    """
    Rebuild the Merkle root from the bundle's event HMACs alone.

    Uses domain/merkle.py's compute_root(), which already applies the
    0x00 / 0x01 leaf/node domain-separation prefixes — the same function
    the server itself uses, so a verifier reproduces the server's
    algorithm exactly rather than a parallel reimplementation that could
    silently drift from it.

    Args:
        events: Bundle event dicts, in ascending sequence order, each
            with "hmac_value".

    Returns:
        The recomputed Merkle root (32 bytes).
    """
    hmac_values = [event["hmac_value"] for event in events]
    return compute_root(hmac_values)


def verify_bundle_signature(
    recomputed_root: bytes,
    signature_hex: str,
    public_key: Ed25519PublicKey,
) -> bool:
    """
    Verify the signature against the LOCALLY RECOMPUTED root.

    This is deliberately not "verify the bundle's claimed signature
    against the bundle's claimed root" — that would only prove the server
    can multiply, since both numbers came from the same place. Passing
    this function the root computed independently by
    recompute_root_from_bundle() is what makes a passing result mean
    something: it proves the signature is valid for data this caller
    derived itself from the individual events.

    Args:
        recomputed_root: The root from recompute_root_from_bundle(), NOT
            the bundle's claimed merkle_root field.
        signature_hex: The bundle's claimed signature (hex).
        public_key: The Ed25519 public key fetched from GET /keys/public.

    Returns:
        True if the signature verifies against the recomputed root.
    """
    try:
        public_key.verify(bytes.fromhex(signature_hex), recomputed_root)
        return True
    except InvalidSignature:
        return False


def verify_bundle(
    events: list[dict],
    claimed_root_hex: str,
    signature_hex: str,
    public_key: Ed25519PublicKey,
    hmac_key: bytes,
) -> VerificationReport:
    """
    Run every check and assemble a full report.

    Args:
        events: Bundle event dicts (sequence, canonical_json, hmac_value),
            ascending sequence order.
        claimed_root_hex: The bundle's stated merkle_root, compared
            against (never used to derive) the independently recomputed
            root.
        signature_hex: The bundle's stated signature.
        public_key: Ed25519 public key from GET /keys/public.
        hmac_key: The key to recompute HMACs with (see
            verify_hmac_chain_continuity's docstring on why this demo
            build can supply one at all).

    Returns:
        A VerificationReport with every check's individual pass/fail and
        an overall verdict.
    """
    checks: list[CheckResult] = []
    first_divergent_sequence: Optional[int] = None

    hmac_chain_passed, hmac_divergence = verify_hmac_chain_continuity(events, hmac_key)
    checks.append(
        CheckResult(
            name="hmac_chain_continuity",
            passed=hmac_chain_passed,
            detail=(
                "Every event's HMAC matches its canonical JSON and the chain."
                if hmac_chain_passed
                else f"HMAC mismatch first detected at sequence {hmac_divergence}."
            ),
        )
    )
    if not hmac_chain_passed and first_divergent_sequence is None:
        first_divergent_sequence = hmac_divergence

    recomputed_root = recompute_root_from_bundle(events)
    recomputed_root_hex = recomputed_root.hex()
    root_matches = recomputed_root_hex == claimed_root_hex
    checks.append(
        CheckResult(
            name="merkle_root_matches",
            passed=root_matches,
            detail=(
                "Recomputed root matches the bundle's claimed root."
                if root_matches
                else f"Recomputed root {recomputed_root_hex} does not match "
                f"claimed root {claimed_root_hex}."
            ),
        )
    )
    # A root mismatch with no HMAC-chain divergence means some event's HMAC
    # is internally self-consistent with the chain but the LEAF SET itself
    # doesn't match what was signed (e.g. an event was reordered or
    # substituted with another valid-looking one) — that cannot be pinned
    # to one sequence number without a full inclusion-proof walk per leaf,
    # which is out of scope for a summary report. first_divergent_sequence
    # stays None in that case; the detail string above still names the
    # mismatch itself.

    signature_valid = verify_bundle_signature(recomputed_root, signature_hex, public_key)
    checks.append(
        CheckResult(
            name="signature_valid",
            passed=signature_valid,
            detail=(
                "Signature verifies against the independently recomputed root."
                if signature_valid
                else "Signature does NOT verify against the independently "
                "recomputed root. Either the root or the signature has "
                "been altered."
            ),
        )
    )

    overall_passed = all(check.passed for check in checks)

    return VerificationReport(
        overall_passed=overall_passed,
        checks=tuple(checks),
        first_divergent_sequence=first_divergent_sequence,
    )
