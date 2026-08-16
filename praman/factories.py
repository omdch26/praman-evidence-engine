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
    2. Add a case here: case "rego": return RegoPolicy Engine()
    3. Set POLICY_ENGINE=rego in .env
    Done. No other changes.
"""

from praman.config import settings


# Placeholder: adapters will be imported and built here.
# For now, we return stubs that allow the app to start without actual adapters.
# This will be populated as we build adapters.


def build_placeholder_adapter():
    """Placeholder for now. Will be replaced as adapters are implemented."""
    return {"status": "adapters will be built here"}
