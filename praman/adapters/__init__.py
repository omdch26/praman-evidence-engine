"""
Concrete implementations of ports/ interfaces.

Responsibility
    Implement each Strategy: policy engines, signers, drift detectors,
    certificate renderers. One file per adapter.
    Import from ports/ and domain/, never from services/ or api/.

Must not
    Be imported by services/ or api/ directly.
    Implementations are constructed only in factories.py.
    Contain business logic — that belongs in services/.

File pattern
    adapters/policy/json_rules.py, adapters/policy/rego.py, adapters/signing/ed25519.py
    Each adapter is swappable; wiring is in factories.py.
"""
