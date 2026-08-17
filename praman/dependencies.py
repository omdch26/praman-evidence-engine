"""
FastAPI dependency providers — process-lifetime singletons for injected adapters.

Responsibility
    Construct adapters once, at import time, and expose them as FastAPI
    dependencies so route handlers receive the same instance on every
    request instead of building a fresh one per call.

Must not
    Contain business logic.
    Be imported by domain/, ports/, or services/ (only by api/routers/).

Why this file exists
    factories.py builds adapters from settings; something has to call it
    exactly once and hand the result to FastAPI's dependency system. This
    is that one call site. The key custody adapter in particular must be
    built once per process, not once per request — see
    adapters/key_custody/environment_key.py for why a fresh key per call
    is the exact bug this whole port exists to prevent.
"""

from praman.config import settings
from praman.factories import build_certificate_renderer, build_key_custody
from praman.ports.certificate_renderer import CertificateRenderer
from praman.ports.key_custody import KeyCustody

# Built once, at import time, for the life of the process. Every request
# that depends on get_key_custody() receives this same object.
_key_custody: KeyCustody = build_key_custody(settings)

# Built once, at import time — rendering is stateless, but constructing it
# per request would be pointless work on every certificate download.
_certificate_renderer: CertificateRenderer = build_certificate_renderer(settings)


def get_key_custody() -> KeyCustody:
    """FastAPI dependency: the process's single KeyCustody instance."""
    return _key_custody


def get_certificate_renderer() -> CertificateRenderer:
    """FastAPI dependency: the process's single CertificateRenderer instance."""
    return _certificate_renderer
