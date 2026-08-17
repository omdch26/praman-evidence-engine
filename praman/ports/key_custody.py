"""
Contract for holding and exposing the Ed25519 signing key.

Responsibility
    Provide a stable signing key for the lifetime of the process, and the
    matching public key material for independent verification.

Must not
    Generate a key on demand (that produces a different key per call, which
    is the exact bug this port exists to prevent — see ADR 0013).
    Perform network calls itself (an HSM/KMS adapter may, but that is its
    own concern, not this contract's).

Why this is an interface
    Every customer we would actually sell to will demand hardware- or
    KMS-held keys before they let us sign anything that matters to them.
    Keeping key custody behind a Protocol means that requirement is a new
    adapter (adapters/key_custody/hsm_kms.py), not a rewrite of every
    caller that currently signs a root.
"""

from typing import Protocol
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class KeyCustody(Protocol):
    """Holds a stable Ed25519 signing key and its public identity."""

    def signing_key(self) -> Ed25519PrivateKey:
        """
        Return the process's signing key.

        Must return the *same* key object (or an equivalent one, byte for
        byte) on every call for the life of the process. A certificate
        signed at request N and a certificate signed at request N+1 must be
        verifiable against the same published public key, or the signature
        proves nothing.

        Returns:
            The Ed25519 private key used to sign Merkle roots.
        """
        ...

    def public_key_pem(self) -> bytes:
        """
        Return the PEM-encoded public key, for publication.

        This is the artefact an independent verifier — a regulator, a
        customer's legal team, a browser running client-side WebCrypto —
        fetches once and checks every signature against. It must be safe to
        expose over an unauthenticated endpoint; a public key is public by
        definition.

        Returns:
            SubjectPublicKeyInfo-format PEM bytes.
        """
        ...

    def key_id(self) -> str:
        """
        Return a short, stable identifier for the current public key.

        Why this exists: key rotation is inevitable eventually, and a
        certificate that does not say which key signed it cannot be
        re-verified once a new key is in use. The id lets a verifier pick
        the right public key out of a set instead of guessing.

        Returns:
            First 16 hex characters of SHA-256 over the public key's DER
            encoding.
        """
        ...
