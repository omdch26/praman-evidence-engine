"""
Construction of concrete adapters from configuration.

Responsibility
    Translate settings into wired-up implementations.
    The single place in the codebase where an adapter class is referenced by name.
    No adapter is imported anywhere else (services receive them injected).

Must not
    Contain business logic.
    Be imported by domain/, ports/, or services/ (only by api/ and main.py).

Why centralised
    A staff engineer adding an adapter changes exactly two files:
    (1) the new adapter file, (2) one branch here.
    Scattered construction is why swapping implementations is hard.

Example: A bank wants OPA instead of JSON rules.
    1. Write adapters/policy/rego.py (implements PolicyEngine protocol)
    2. Add a case here: case "rego": return RegoPolicyEngine()
    3. Set POLICY_ENGINE=rego in .env
    Done. No other changes.
"""

from praman.config import Settings
from praman.ports.key_custody import KeyCustody


def build_key_custody(settings: Settings) -> KeyCustody:
    """
    Select the key custody adapter named in configuration.

    Raises on an unknown provider rather than falling back to a default:
    a deployment that thinks it configured HSM custody but silently got
    environment-variable custody instead is a security regression, not a
    convenience.

    Args:
        settings: Application settings (config.py).

    Returns:
        A KeyCustody implementation, constructed and ready to sign.

    Raises:
        ConfigurationError: If the environment adapter is selected and its
            required environment variable is missing or malformed.
        NotImplementedError: If "hsm_kms" is selected (documented, not built).
        ValueError: If key_custody_provider names an adapter that does not exist.
    """
    match settings.key_custody_provider:
        case "environment":
            from praman.adapters.key_custody.environment_key import EnvironmentKeyCustody

            return EnvironmentKeyCustody(settings.ed25519_private_key_pem)
        case "hsm_kms":
            from praman.adapters.key_custody.hsm_kms import HsmKmsKeyCustody

            return HsmKmsKeyCustody()
        case unknown:
            raise ValueError(f"Unknown key_custody_provider: {unknown!r}")
