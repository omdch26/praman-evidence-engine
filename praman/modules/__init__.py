"""
Module registration system.

Responsibility
    Load and register independent modules at startup.
    Each module is self-contained: has its own routes, services, and config.
    Modules share domain/, ports/, and adapters/ (the spine).

Constraint
    Modules must not import each other.
    Module 1 (privacy) and Module 2 (ai_risk) are independently deployable.
    They communicate only through shared domain/ and services/ interfaces.

Pattern
    from praman.modules import ModuleRegistry
    registry = ModuleRegistry()
    registry.register(PrivacyModule())
    registry.register(AiRiskModule())
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ModuleRegistration:
    """Metadata for a registered module."""

    name: str
    version: str
    enabled: bool
    description: str
