"""
HSM/KMS-backed key custody — documented, not implemented.

Responsibility (once built)
    Hold the Ed25519 signing key inside an HSM or cloud KMS (AWS KMS,
    GCP Cloud KMS, Azure Key Vault) so the private key material never
    exists in application process memory at all.

Must not (once built)
    Export the private key in any form. The whole point of this adapter
    is that signing happens inside the HSM/KMS boundary; the private key
    bytes never cross into this process.

Why this is not implemented yet
    Ed25519 support varies by provider and by HSM model — some support it
    natively, some require ECDSA P-256 instead (which changes the
    verification story: WebCrypto's Ed25519 support does not extend to
    P-256 the same way, so the frontend verifier in demo.html would need
    a second code path). Committing to one provider's API before a real
    customer names their HSM vendor would be guessing, not designing.

Production approach
    1. Pick the provider per the customer's existing key-management
       infrastructure (most banks already run one of AWS KMS, Azure Key
       Vault, or an on-prem HSM via PKCS#11).
    2. Implement `signing_key()` NOT by loading a private key object, but
       by returning a thin wrapper whose `.sign()` calls out to the
       HSM/KMS API. This means the KeyCustody protocol's `signing_key()`
       return type may need to widen from `Ed25519PrivateKey` to a
       narrower "can sign" Protocol once this adapter exists — flagged
       here so the next engineer isn't surprised by that port change.
    3. `public_key_pem()` and `key_id()` are unaffected — the public key
       is exported once at provisioning time and cached exactly as
       EnvironmentKeyCustody does.

See also
    docs/ADR/0014-key-custody-port.md
    ports/key_custody.py
    adapters/key_custody/environment_key.py — the adapter that ships now
"""

from praman.ports.key_custody import KeyCustody  # noqa: F401 — documents intended interface


class HsmKmsKeyCustody:
    """Not implemented. See module docstring for what building this requires."""

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "HSM/KMS key custody is designed but not implemented. "
            "See adapters/key_custody/hsm_kms.py module docstring and "
            "docs/ADR/0014-key-custody-port.md for what shipping this requires."
        )
