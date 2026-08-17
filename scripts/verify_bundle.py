#!/usr/bin/env python3
"""
Standalone, offline verifier for a Praman evidence bundle.

Responsibility
    Independently confirm that a downloaded evidence bundle's Merkle root
    and Ed25519 signature are genuine, using nothing but the standard
    library, the `cryptography` package, and the bundle file itself.

Must not
    Import anything from the `praman` package. A verifier that shares
    code with the system it verifies proves less than one that
    reimplements the algorithm independently — if this script imported
    praman.domain.merkle, a bug that made both the server and the
    verifier agree on a wrong answer would be invisible. Reimplementing
    the spec from scratch here means this script and the server's own
    logic can only agree by both being correct, not by construction.

Usage
    python scripts/verify_bundle.py bundle.json --public-key key.pem

    Exit code 0 on full pass, 1 on any check failing. Prints a per-check
    breakdown either way — never just "PASS" or "FAIL" with no detail,
    because a verifier that only says "no" without saying where is not
    much more useful than the CSS-only button this whole effort replaced.

See also
    docs/VERIFICATION.md — the human-readable spec this implements,
    including a worked two-event example with real hex values.
    praman/domain/verification.py — the specification this file
    independently reimplements (see that module's docstring for why the
    two are not shared code).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Domain-separation prefixes for Merkle leaf/internal-node hashing.
# Must match praman/domain/merkle.py's LEAF_PREFIX / NODE_PREFIX exactly —
# this is the one place independence has a real cost: if that file's
# prefixes ever change, this script has to be updated by hand, because it
# deliberately does not import them.
LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

# The disclosed fixed demo HMAC key (see docs/LIMITATIONS.md). A bundle
# produced against a real per-tenant key would need that key supplied
# separately; this default only applies to bundles from this demo build.
DEMO_HMAC_KEY = b"\x00" * 32


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def hash_leaf(hmac_hex: str) -> bytes:
    """SHA-256 over LEAF_PREFIX + the HMAC bytes."""
    return hashlib.sha256(LEAF_PREFIX + bytes.fromhex(hmac_hex)).digest()


def hash_node(left: bytes, right: bytes) -> bytes:
    """SHA-256 over NODE_PREFIX + left + right."""
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def compute_merkle_root(hmac_hex_list: list[str]) -> bytes:
    """
    Rebuild the Merkle root from a list of event HMACs.

    Odd node counts duplicate the last element (the CT convention),
    matching praman/domain/merkle.py's compute_root().
    """
    if not hmac_hex_list:
        raise ValueError("Cannot compute a root over zero events")

    level = [hash_leaf(h) for h in hmac_hex_list]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(hash_node(left, right))
        level = next_level
    return level[0]


def compute_hmac_hex(canonical_bytes: bytes, key: bytes, previous_hmac_hex: str | None) -> str:
    """HMAC-SHA256, chained: message = previous_hmac_bytes + canonical_bytes."""
    message = bytes.fromhex(previous_hmac_hex) + canonical_bytes if previous_hmac_hex else canonical_bytes
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_hmac_chain(events: list[dict[str, Any]], hmac_key: bytes) -> tuple[bool, int | None]:
    """Recompute each event's HMAC and compare to its claimed value, honouring the chain."""
    previous_hmac_hex: str | None = None
    for event in events:
        canonical_bytes = event["canonical_json"].encode("utf-8")
        recomputed = compute_hmac_hex(canonical_bytes, hmac_key, previous_hmac_hex)
        if recomputed != event["hmac_value"]:
            return False, event["sequence"]
        previous_hmac_hex = event["hmac_value"]
    return True, None


def verify_signature(recomputed_root: bytes, signature_hex: str, public_key: Ed25519PublicKey) -> bool:
    """
    Verify the signature against the LOCALLY recomputed root — never the
    bundle's claimed root. See domain/verification.py's docstring on why
    that distinction is the entire point of independent verification.
    """
    try:
        public_key.verify(bytes.fromhex(signature_hex), recomputed_root)
        return True
    except InvalidSignature:
        return False


def verify_bundle(
    bundle: dict[str, Any],
    public_key: Ed25519PublicKey,
    hmac_key: bytes = DEMO_HMAC_KEY,
) -> list[CheckResult]:
    """Run every check and return the full breakdown, in order."""
    checks: list[CheckResult] = []
    events = bundle["events"]

    hmac_passed, hmac_divergence = verify_hmac_chain(events, hmac_key)
    checks.append(
        CheckResult(
            name="hmac_chain_continuity",
            passed=hmac_passed,
            detail=(
                "Every event's HMAC matches its canonical JSON and the chain."
                if hmac_passed
                else f"HMAC mismatch first detected at sequence {hmac_divergence}."
            ),
        )
    )

    recomputed_root = compute_merkle_root([e["hmac_value"] for e in events])
    recomputed_root_hex = recomputed_root.hex()
    root_matches = recomputed_root_hex == bundle["merkle_root"]
    checks.append(
        CheckResult(
            name="merkle_root_matches",
            passed=root_matches,
            detail=(
                "Recomputed root matches the bundle's claimed root."
                if root_matches
                else f"Recomputed root {recomputed_root_hex} != claimed root {bundle['merkle_root']}."
            ),
        )
    )

    signature_valid = verify_signature(recomputed_root, bundle["signature"], public_key)
    checks.append(
        CheckResult(
            name="signature_valid",
            passed=signature_valid,
            detail=(
                "Signature verifies against the independently recomputed root."
                if signature_valid
                else "Signature does NOT verify against the independently recomputed root."
            ),
        )
    )

    return checks


def _load_public_key(path: str) -> Ed25519PublicKey:
    with open(path, "rb") as f:
        key = load_pem_public_key(f.read())
    if not isinstance(key, Ed25519PublicKey):
        raise SystemExit(f"error: {path} is not an Ed25519 public key")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify a Praman evidence bundle, offline.",
    )
    parser.add_argument("bundle", help="Path to a downloaded evidence bundle JSON file")
    parser.add_argument("--public-key", required=True, help="Path to the Ed25519 public key PEM (from GET /keys/public)")
    parser.add_argument(
        "--hmac-key-hex",
        default=None,
        help="Hex-encoded HMAC key, if not using the disclosed fixed demo key "
        "(32 bytes of zeros — see docs/LIMITATIONS.md)",
    )
    args = parser.parse_args()

    with open(args.bundle, encoding="utf-8") as f:
        bundle = json.load(f)

    public_key = _load_public_key(args.public_key)
    hmac_key = bytes.fromhex(args.hmac_key_hex) if args.hmac_key_hex else DEMO_HMAC_KEY

    print(f"Verifying bundle for tenant {bundle.get('tenant_id', '?')} "
          f"({len(bundle.get('events', []))} events, key_id {bundle.get('key_id', '?')})\n")

    checks = verify_bundle(bundle, public_key, hmac_key)

    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"  [{status}] {check.name}: {check.detail}")

    overall_passed = all(c.passed for c in checks)
    print(f"\n{'PASSED' if overall_passed else 'FAILED'}")

    return 0 if overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
