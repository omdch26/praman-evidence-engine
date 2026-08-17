"""
Tests for scripts/verify_bundle.py.

Run as subprocess invocations — the same way a real user runs this
script — rather than importing its functions directly, because the whole
point of this script is that it works as a standalone CLI tool with no
dependency on the rest of this repository being importable.

Also proves the standalone verifier agrees with domain/verification.py on
the same inputs, per CLAUDE_CODE_PROMPT_verifiable_demo.md's required
test list.

Run with: pytest tests/scripts/test_verify_bundle.py -v
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praman.domain.canonical import canonicalise
from praman.domain.hashing import compute_hmac_hex
from praman.domain.merkle import compute_root_hex
from praman.domain.signing import public_key_to_pem, sign_root_hex
from praman.domain.verification import verify_bundle as domain_verify_bundle

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_bundle.py"
_HMAC_KEY = b"\x00" * 32


def _build_bundle_and_key(tmp_path: Path, event_count: int = 4) -> tuple[Path, Path, dict]:
    """Build a real bundle + PEM key on disk, exactly matching evidence_service.py's shape."""
    private_key = Ed25519PrivateKey.generate()

    events = []
    previous_hmac_hex = None
    for i in range(event_count):
        payload = {"event_type": f"event_{i}", "seq": i}
        canonical_bytes = canonicalise(payload)
        hmac_hex = compute_hmac_hex(canonical_bytes, _HMAC_KEY, previous_hmac_hex)
        events.append(
            {
                "sequence": i,
                "canonical_json": canonical_bytes.decode("utf-8"),
                "hmac_value": hmac_hex,
            }
        )
        previous_hmac_hex = hmac_hex

    root_hex = compute_root_hex([e["hmac_value"] for e in events])
    signature_hex = sign_root_hex(root_hex, private_key)

    bundle = {
        "bundle_version": "1.0",
        "tenant_id": "demo-testfile",
        "events": events,
        "merkle_root": root_hex,
        "signature": signature_hex,
        "key_id": "test0000",
    }

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    key_path = tmp_path / "key.pem"
    key_path.write_bytes(public_key_to_pem(private_key.public_key()))

    return bundle_path, key_path, bundle


def _run_script(bundle_path: Path, key_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(bundle_path), "--public-key", str(key_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestVerifyBundleScript:
    def test_untampered_bundle_exits_zero(self, tmp_path):
        bundle_path, key_path, _ = _build_bundle_and_key(tmp_path)

        result = _run_script(bundle_path, key_path)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout
        assert "[PASS] hmac_chain_continuity" in result.stdout
        assert "[PASS] merkle_root_matches" in result.stdout
        assert "[PASS] signature_valid" in result.stdout

    def test_tampered_bundle_exits_one_and_names_sequence(self, tmp_path):
        bundle_path, key_path, bundle = _build_bundle_and_key(tmp_path)

        bundle["events"][1]["hmac_value"] = "a" * 64
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

        result = _run_script(bundle_path, key_path)

        assert result.returncode == 1
        assert "FAILED" in result.stdout
        assert "sequence 1" in result.stdout
        assert "[FAIL] hmac_chain_continuity" in result.stdout
        assert "[FAIL] merkle_root_matches" in result.stdout
        assert "[FAIL] signature_valid" in result.stdout

    def test_script_does_not_import_praman(self):
        """
        The central design claim: this script must never import from the
        praman package. Checked by static inspection of the actual import
        statements, not by trusting the docstring.
        """
        import ast

        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        imported_modules = [
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        ] + [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]

        assert not any(module.startswith("praman") for module in imported_modules), (
            f"verify_bundle.py must not import from praman/, found: {imported_modules}"
        )


class TestStandaloneVerifierAgreesWithDomainVerifier:
    def test_standalone_verifier_agrees_with_domain_verifier(self, tmp_path):
        """
        The same bundle, checked by both the standalone script (subprocess)
        and domain/verification.py (in-process), must reach the same
        verdict on both the untampered and tampered cases.
        """
        bundle_path, key_path, bundle = _build_bundle_and_key(tmp_path)

        # In-process domain verification
        from praman.domain.signing import public_key_from_pem

        public_key = public_key_from_pem(key_path.read_bytes())
        domain_report = domain_verify_bundle(
            events=bundle["events"],
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=_HMAC_KEY,
        )

        # Standalone script, subprocess
        script_result = _run_script(bundle_path, key_path)

        assert domain_report.overall_passed is True
        assert script_result.returncode == 0

        # Now tamper both the same way and confirm both fail together
        bundle["events"][2]["hmac_value"] = "c" * 64
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

        domain_report_tampered = domain_verify_bundle(
            events=bundle["events"],
            claimed_root_hex=bundle["merkle_root"],
            signature_hex=bundle["signature"],
            public_key=public_key,
            hmac_key=_HMAC_KEY,
        )
        script_result_tampered = _run_script(bundle_path, key_path)

        assert domain_report_tampered.overall_passed is False
        assert domain_report_tampered.first_divergent_sequence == 2
        assert script_result_tampered.returncode == 1
        assert "sequence 2" in script_result_tampered.stdout
