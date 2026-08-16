-- Migration 001: Initial schema
-- Purpose: Create events table (append-only), RLS policies, indexes
-- Timestamp: 2026-08-10

-- Events table: append-only ledger of all events
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    module VARCHAR(50) NOT NULL,  -- "privacy" or "ai_risk"
    event_type VARCHAR(100) NOT NULL,  -- "consent_granted", "policy_evaluated", etc.
    canonical_event JSONB NOT NULL,  -- Deterministic JSON serialisation
    hmac_value VARCHAR(255) NOT NULL,  -- HMAC-SHA256 of canonical event
    signature VARCHAR(255),  -- Ed25519 signature (nullable, computed later)
    merkle_root VARCHAR(255),  -- Merkle root at time of event (nullable, computed later)
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Constraint: cannot update or delete (append-only)
    CONSTRAINT no_update_delete CHECK (true)  -- Will be enforced by trigger
);

-- Indexes for common queries
CREATE INDEX idx_events_tenant_id ON events(tenant_id);
CREATE INDEX idx_events_module ON events(module);
CREATE INDEX idx_events_event_type ON events(event_type);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_tenant_timestamp ON events(tenant_id, timestamp);

-- Append-only trigger: prevent UPDATE and DELETE
CREATE OR REPLACE FUNCTION prevent_update_delete()
    RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Ledger is append-only: UPDATE is not allowed on events table';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Ledger is append-only: DELETE is not allowed on events table';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_events_append_only
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW
    EXECUTE FUNCTION prevent_update_delete();

-- Row Level Security (RLS): tenant isolation
-- Each tenant can only see their own events (even within the app, this prevents cross-tenant leaks)
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- Policy: tenant can only read their own events
CREATE POLICY events_tenant_isolation ON events
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant_id', true));

-- Policy: tenant can only insert into their own tenant
CREATE POLICY events_tenant_insert ON events
    FOR INSERT
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));

-- Certificates table: BSA §63 certificates (one per merkle root)
CREATE TABLE IF NOT EXISTS certificates (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    merkle_root VARCHAR(255) NOT NULL UNIQUE,  -- Uniquely identifies a root
    ed25519_signature VARCHAR(255) NOT NULL,  -- Signature of the root
    rfc3161_timestamp TEXT,  -- RFC 3161 anchor (JSON or binary, stored as text)
    certificate_pdf BYTEA,  -- PDF bytes (nullable, generated on demand)
    part_b_signed BOOLEAN DEFAULT FALSE,  -- Has the customer signed Part B?
    part_b_signed_by VARCHAR(255),  -- Name of signatory
    part_b_signed_at TIMESTAMP,  -- When Part B was signed
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_certificates_tenant_id ON certificates(tenant_id);
CREATE INDEX idx_certificates_merkle_root ON certificates(merkle_root);

-- RLS on certificates
ALTER TABLE certificates ENABLE ROW LEVEL SECURITY;

CREATE POLICY certificates_tenant_isolation ON certificates
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY certificates_tenant_insert ON certificates
    FOR INSERT
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY certificates_tenant_update ON certificates
    FOR UPDATE
    USING (tenant_id = current_setting('app.current_tenant_id', true));

-- Tenants table: metadata about tenants
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    hmac_key_hash VARCHAR(255),  -- Hash of the HMAC key (never store the key itself)
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Policies table: governance rules per tenant
CREATE TABLE IF NOT EXISTS policies (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    policy_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rule JSONB NOT NULL,  -- Policy rule (operators, conditions, etc.)
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT policies_tenant_id_fk FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_policies_tenant_id ON policies(tenant_id);
CREATE INDEX idx_policies_policy_id ON policies(policy_id);

-- RLS on policies
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;

CREATE POLICY policies_tenant_isolation ON policies
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant_id', true));

-- Comment on the schema
COMMENT ON TABLE events IS
    'Append-only ledger of all events. Each event is cryptographically chained with HMAC. '
    'This table must never allow UPDATE or DELETE. RLS ensures tenant isolation.';

COMMENT ON TABLE certificates IS
    'BSA §63 certificates. One certificate per Merkle root. Contains hash, algorithm, '
    'signature, timestamp, and customer attestation (Part B).';

COMMENT ON TABLE tenants IS
    'Tenant metadata. Each tenant has an isolated ledger and policy space.';

COMMENT ON TABLE policies IS
    'Governance policies. Define which actions are allowed for agents and data operations.';
