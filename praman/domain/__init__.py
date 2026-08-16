"""
Pure domain logic — no I/O, no framework, no database.

Responsibility
    Cryptographic primitives and event models. No side effects.
    All functions are deterministic and unit-testable in isolation.

Must not
    Import from services/, adapters/, api/, or persistence/.
    Make network calls, access databases, or perform I/O.
    Know about FastAPI, SQLAlchemy, or any framework.

Example imports from this layer go: domain.hashing, domain.merkle, domain.models
"""
