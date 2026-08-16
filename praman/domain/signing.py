"""
Ed25519 signing and verification for Merkle roots.

Responsibility
    Generate Ed25519 keypairs.
    Sign Merkle roots (proving the root was not modified after signing).
    Verify signatures (anyone can verify, using the public key).
    Manage keypairs securely (private key never leaves process).

Must not
    Perform I/O or network calls (that is the responsibility of adapters).
    Store the private key on disk here (that is config's job).
    Share the private key (only signature methods use it).

Design notes
    Ed25519 is chosen over ECDSA/RSA because:
    1. No parameter choices to get wrong (no curve selection)
    2. No catastrophic nonce-reuse failure mode (ECDSA's Achilles heel)
    3. Small signatures (64 bytes) and fast
    4. Designed specifically for this use case

    The public key is published so anyone (including opposing counsel)
    can verify a root was not substituted. This is the non-repudiation
    property that makes evidence admissible.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
import base64
from typing import Tuple, Optional


def generate_keypair() -> Tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """
    Generate an Ed25519 keypair.

    Returns:
        Tuple of (private_key, public_key)

    Example:
        >>> private, public = generate_keypair()
        >>> type(private).__name__
        'Ed25519PrivateKey'
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key


def private_key_to_pem(private_key: ed25519.Ed25519PrivateKey) -> bytes:
    """
    Export a private key to PEM format (PKCS8).

    PEM format is the standard for key exchange and storage.

    Args:
        private_key: Ed25519 private key.

    Returns:
        bytes: PEM-encoded private key (including "-----BEGIN PRIVATE KEY-----" header).

    Example:
        >>> private, _ = generate_keypair()
        >>> pem = private_key_to_pem(private)
        >>> pem[:27]
        b'-----BEGIN PRIVATE KEY-----'
    """
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem


def private_key_from_pem(pem: bytes) -> ed25519.Ed25519PrivateKey:
    """
    Import a private key from PEM format.

    Args:
        pem: PEM-encoded private key (bytes).

    Returns:
        ed25519.Ed25519PrivateKey

    Raises:
        ValueError: If PEM is malformed.

    Example:
        >>> private, _ = generate_keypair()
        >>> pem = private_key_to_pem(private)
        >>> recovered = private_key_from_pem(pem)
        >>> recovered is private  # False (different object)
    """
    private_key = serialization.load_pem_private_key(pem, password=None)
    return private_key


def public_key_to_pem(public_key: ed25519.Ed25519PublicKey) -> bytes:
    """
    Export a public key to PEM format (SubjectPublicKeyInfo).

    Args:
        public_key: Ed25519 public key.

    Returns:
        bytes: PEM-encoded public key.
    """
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem


def public_key_from_pem(pem: bytes) -> ed25519.Ed25519PublicKey:
    """
    Import a public key from PEM format.

    Args:
        pem: PEM-encoded public key (bytes).

    Returns:
        ed25519.Ed25519PublicKey
    """
    public_key = serialization.load_pem_public_key(pem)
    return public_key


def sign_root(root_hex: str, private_key: ed25519.Ed25519PrivateKey) -> bytes:
    """
    Sign a Merkle root.

    Args:
        root_hex: Root hash as hex string (64 characters / 32 bytes).
        private_key: Ed25519 private key.

    Returns:
        bytes: Signature (64 bytes).

    Example:
        >>> root = "abc123" * 10 + "abc1"
        >>> private, _ = generate_keypair()
        >>> signature = sign_root(root, private)
        >>> len(signature)
        64
    """
    root_bytes = bytes.fromhex(root_hex)
    signature = private_key.sign(root_bytes)
    return signature


def sign_root_hex(root_hex: str, private_key: ed25519.Ed25519PrivateKey) -> str:
    """
    Sign a Merkle root and return signature as hex string.

    Convenience wrapper for sign_root().

    Args:
        root_hex: Root hash as hex string.
        private_key: Ed25519 private key.

    Returns:
        str: Signature as hex string (128 characters).
    """
    signature = sign_root(root_hex, private_key)
    return signature.hex()


def verify_signature(
    root_hex: str,
    signature: bytes,
    public_key: ed25519.Ed25519PublicKey,
) -> bool:
    """
    Verify a signature on a Merkle root.

    Args:
        root_hex: Root hash as hex string.
        signature: Signature bytes (64 bytes).
        public_key: Ed25519 public key.

    Returns:
        bool: True if signature is valid, False otherwise.

    Example:
        >>> root = "abc123" * 10 + "abc1"
        >>> private, public = generate_keypair()
        >>> signature = sign_root(root, private)
        >>> verify_signature(root, signature, public)
        True
    """
    try:
        root_bytes = bytes.fromhex(root_hex)
        public_key.verify(signature, root_bytes)
        return True
    except InvalidSignature:
        return False


def verify_signature_hex(
    root_hex: str,
    signature_hex: str,
    public_key: ed25519.Ed25519PublicKey,
) -> bool:
    """
    Verify a signature (hex-encoded) on a Merkle root.

    Convenience wrapper for verify_signature().

    Args:
        root_hex: Root hash as hex string.
        signature_hex: Signature as hex string (128 characters).
        public_key: Ed25519 public key.

    Returns:
        bool: True if valid.
    """
    signature = bytes.fromhex(signature_hex)
    return verify_signature(root_hex, signature, public_key)


def tampering_check(
    root_hex: str,
    signature_hex: str,
    public_key: ed25519.Ed25519PublicKey,
) -> Tuple[bool, str]:
    """
    Check if a root has been tampered with (verify signature).

    Returns a tuple (is_valid, message) for human-readable output.

    Args:
        root_hex: Root hash as hex string.
        signature_hex: Signature as hex string.
        public_key: Ed25519 public key.

    Returns:
        Tuple of (is_valid, message).

    Example:
        >>> root = "abc123" * 10 + "abc1"
        >>> private, public = generate_keypair()
        >>> signature = sign_root_hex(root, private)
        >>> valid, msg = tampering_check(root, signature, public)
        >>> valid
        True
        >>> msg
        'Root signature is valid'
    """
    is_valid = verify_signature_hex(root_hex, signature_hex, public_key)

    if is_valid:
        return True, "Root signature is valid — evidence has not been tampered with."
    else:
        return False, "Root signature verification failed — evidence may have been tampered with."
