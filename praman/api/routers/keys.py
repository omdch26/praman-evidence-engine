"""
Public key publication — GET /keys/public.

Responsibility
    Serve the process's Ed25519 public key and key_id, unauthenticated,
    cacheable. This is the artefact every other verification step in the
    system (certificate signatures, evidence bundle signatures) is
    checked against.

Must not
    Require authentication. A public key is public by definition; gating
    it behind auth would defeat the purpose of independent verification —
    a regulator or a customer's legal team must be able to fetch it
    without an account.
    Ever return the private key or anything derived from it beyond the
    public key and its id.
"""

from fastapi import APIRouter, Depends

from praman.dependencies import get_key_custody
from praman.ports.key_custody import KeyCustody

router = APIRouter()


@router.get("/public")
async def get_public_key(key_custody: KeyCustody = Depends(get_key_custody)) -> dict:
    """
    Return the current signing key's public identity.

    Unauthenticated and safe to cache — the response only ever changes
    when the key rotates (not implemented yet; see ADR 0014).

    Returns:
        key_id: Short stable identifier for this public key.
        algorithm: Always "Ed25519" for this build.
        public_key_pem: SubjectPublicKeyInfo-format PEM.
        public_key_raw_hex: The raw 32-byte public key, hex-encoded — the
            form WebCrypto's importKey({name: "Ed25519"}, ...) expects for
            the "raw" format, so the browser verifier does not need a PEM
            parser.
    """
    public_key_pem = key_custody.public_key_pem()

    from praman.domain.signing import public_key_from_pem
    from cryptography.hazmat.primitives import serialization

    public_key_obj = public_key_from_pem(public_key_pem)
    raw_bytes = public_key_obj.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return {
        "key_id": key_custody.key_id(),
        "algorithm": "Ed25519",
        "public_key_pem": public_key_pem.decode("utf-8"),
        "public_key_raw_hex": raw_bytes.hex(),
    }
