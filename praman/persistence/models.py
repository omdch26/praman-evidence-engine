"""
SQLAlchemy ORM models for Praman.

Responsibility
    Define database models (Event, Certificate, Tenant, Policy).
    No business logic; only data structure and relationships.
    Models are used by repositories to persist domain entities.

Must not
    Contain business logic or validation (that is services/).
    Import from services/ or api/.
    Be used directly by services (services use repositories, which use models).

Pattern
    persistence.models.Event (ORM model) ← adapters.repository.* (repository) ← services.*
    Services never touch models directly.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, LargeBinary, ForeignKey, func, event, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Event(Base):
    """
    Ledger event — append-only record of an action.

    Attributes
        tenant_id: Which customer owns this event
        module: "privacy" or "ai_risk"
        event_type: What happened (consent_granted, policy_evaluated, etc.)
        canonical_event: Deterministic JSON
        hmac_value: HMAC chaining
        signature: Ed25519 signature (optional)
        merkle_root: Root at time of event (optional)
        timestamp: When it happened (per event, not system time)
        created_at: When it was written to DB
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    module = Column(String(50), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    canonical_event = Column(JSONB, nullable=False)
    hmac_value = Column(String(255), nullable=False)
    signature = Column(String(255), nullable=True)
    merkle_root = Column(String(255), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_events_tenant_timestamp', 'tenant_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<Event {self.id}: {self.event_type} @ {self.timestamp}>"


class Certificate(Base):
    """
    BSA §63 certificate — proof of event system operation.

    Attributes
        tenant_id: Which customer owns this certificate
        merkle_root: The root this certificate proves
        ed25519_signature: Signature on the root
        rfc3161_timestamp: Independent time proof
        certificate_pdf: Rendered PDF (ByteA, nullable)
        part_b_signed: Customer attestation (Part B) is signed
        part_b_signed_by: Name of signatory
        part_b_signed_at: When it was signed
    """

    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    merkle_root = Column(String(255), nullable=False, unique=True)
    ed25519_signature = Column(String(255), nullable=False)
    rfc3161_timestamp = Column(String(1024), nullable=True)
    certificate_pdf = Column(LargeBinary, nullable=True)
    part_b_signed = Column(Boolean, default=False)
    part_b_signed_by = Column(String(255), nullable=True)
    part_b_signed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_certificates_tenant_root', 'tenant_id', 'merkle_root'),
    )

    def __repr__(self):
        return f"<Certificate {self.id}: root={self.merkle_root[:8]}...>"


class Tenant(Base):
    """
    Tenant metadata — one per customer.

    Attributes
        tenant_id: Unique identifier (usually org domain or UUID)
        name: Display name
        description: What this tenant is for
        hmac_key_hash: Hash of the client's HMAC key (never store the key itself)
        enabled: Is this tenant active?
    """

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    hmac_key_hash = Column(String(255), nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Tenant {self.tenant_id}>"


class Policy(Base):
    """
    Governance policy — rule for what an agent may do.

    Attributes
        tenant_id: Which customer owns this policy
        policy_id: Unique identifier within the tenant
        name: Display name
        description: What this policy enforces
        rule: JSONB rule object (operators, conditions, thresholds)
        enabled: Is this policy active?
    """

    __tablename__ = "policies"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False, index=True, foreign_key="tenants.tenant_id")
    policy_id = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    rule = Column(JSONB, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_policies_tenant_policy_id', 'tenant_id', 'policy_id'),
    )

    def __repr__(self):
        return f"<Policy {self.policy_id}>"
