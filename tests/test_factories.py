"""
Tests for factories.py — adapter construction from settings.

Proves the factory raises on unknown configuration rather than silently
falling back to a default (CLAUDE.md's fail-fast principle for
misconfiguration).

Run with: pytest tests/test_factories.py -v
"""

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praman.config import Settings
from praman.factories import build_certificate_renderer, build_key_custody
from praman.adapters.key_custody.environment_key import EnvironmentKeyCustody
from praman.adapters.certificate.reportlab_renderer import ReportLabCertificateRenderer


def _settings_with(**overrides) -> Settings:
    """Build a Settings instance for testing, without touching the real .env."""
    base = {
        "database_url": "postgresql://user:pass@localhost/db",
    }
    base.update(overrides)
    return Settings(**base)


def _valid_key_pem_base64() -> str:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode()


class TestBuildKeyCustody:
    def test_environment_provider_returns_environment_key_custody(self):
        settings = _settings_with(
            key_custody_provider="environment",
            ed25519_private_key_pem=_valid_key_pem_base64(),
        )

        custody = build_key_custody(settings)

        assert isinstance(custody, EnvironmentKeyCustody)

    def test_hsm_kms_provider_raises_not_implemented(self):
        settings = _settings_with(key_custody_provider="hsm_kms")

        with pytest.raises(NotImplementedError):
            build_key_custody(settings)

    def test_unknown_provider_raises_value_error(self):
        settings = _settings_with(key_custody_provider="quantum_vault")

        with pytest.raises(ValueError, match="Unknown key_custody_provider"):
            build_key_custody(settings)


class TestBuildCertificateRenderer:
    def test_reportlab_provider_returns_reportlab_renderer(self):
        settings = _settings_with(certificate_renderer_provider="reportlab")

        renderer = build_certificate_renderer(settings)

        assert isinstance(renderer, ReportLabCertificateRenderer)

    def test_unknown_provider_raises_value_error(self):
        settings = _settings_with(certificate_renderer_provider="latex")

        with pytest.raises(ValueError, match="Unknown certificate_renderer_provider"):
            build_certificate_renderer(settings)
