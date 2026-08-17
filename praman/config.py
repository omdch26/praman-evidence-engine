"""
Configuration management — settings loaded from environment.

Responsibility
    Type-safe settings from environment variables.
    Never store secrets in code; always use environment.
    All configuration is validated at startup.

Must not
    Contain business logic.
    Fall back to hardcoded defaults for critical settings (fail fast).
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings, validated and typed."""

    # --- Application
    environment: str = "development"  # development or production
    debug: bool = False
    version: str = "0.1.0"
    port: int = 8000
    workers: int = 2
    log_level: str = "info"

    # --- Database (Neon Postgres)
    database_url: str  # Must be provided; no default
    # Connection pool sizes
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False  # Log all SQL if True

    # --- Cryptography
    ed25519_private_key_path: Optional[str] = None  # Path to private key file
    hmac_key: Optional[str] = None  # Client-provided HMAC key (base64-encoded)
    # Ed25519 signing key: PEM, then base64-encoded (survives env-var transport
    # without newline-mangling). Required for KEY_CUSTODY_PROVIDER=environment.
    # See adapters/key_custody/environment_key.py and docs/DEPLOYMENT.md for
    # how to generate one.
    ed25519_private_key_pem: Optional[str] = None
    key_custody_provider: str = "environment"  # "environment" | "hsm_kms" (not implemented)

    # --- Demo mode (see api/routers/demonstration.py)
    # Defaults False: an endpoint that attempts a live UPDATE against the
    # ledger must be opt-in, never on by accident in a customer deployment.
    demo_mode_enabled: bool = False

    # --- Modules (enable/disable)
    module_privacy_enabled: bool = True
    module_ai_risk_enabled: bool = True

    # --- OpenTelemetry (Development status)
    otel_enabled: bool = False  # Disabled by default in dev
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"  # Local collector
    otel_service_name: str = "praman-api"
    otel_environment: str = environment  # development or production

    # --- Feature flags
    enable_rls: bool = True  # Row Level Security for tenant isolation
    enable_audit_logging: bool = False  # Admin action trails (not yet implemented)

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def validate_on_init(self) -> None:
        """
        Validate critical settings at startup.

        Fails loudly if DATABASE_URL is missing or malformed.
        Fail-fast principle: misconfiguration = immediate error, not silent fallback.
        """
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is required. Set it in .env or as an environment variable."
            )
        if not self.database_url.startswith("postgresql://"):
            raise ValueError(
                f"DATABASE_URL must be PostgreSQL. Got: {self.database_url[:20]}..."
            )

    def is_production(self) -> bool:
        """True if environment is production."""
        return self.environment == "production"

    def is_development(self) -> bool:
        """True if environment is development."""
        return self.environment == "development"


# Global settings instance. Loaded once at startup.
settings = Settings()
settings.validate_on_init()
