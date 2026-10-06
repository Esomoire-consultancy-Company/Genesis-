import base64
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from genesis_qualification_authority import (
    ATTESTATION_SCHEMA, AuthorityError, canonical_json, evaluate_attestation,
    qualification_digest, validate_authority_registry,
)

REGISTRY = json.loads(Path("config/provider_registry.json").read_text())
QUALIFICATION = json.loads(Path("config/railway_qualification.json").read_text())
AUTHORITIES = json.loads(Path("config/qualification_authorities.json").read_text())
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

def signed_fixture():
    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode()
    authorities = {
        "schema_version": "genesis.qualification-authority-registry.r0.6",
        "registry_id": "TEST", "state": "ACTIVE",
        "authorities": [{
            "authority_id": "AUTH-TEST-001", "state": "ACTIVE", "algorithm": "Ed25519",
            "public_key_b64": public_b64,
            "scope": {"domains": ["CLOUD"], "capabilities": ["APPLICATION_RUNTIME"]},
        }],
    }
    qualification = copy.deepcopy(QUALIFICATION)
    for check in qualification["checks"].values():
        check["result"], check["evidence_refs"] = "PASS", ["test:evidence"]
    claim = {
        "authority_id": "AUTH-TEST-001",
        "qualification_id": qualification["qualification_id"],
        "provider_id": qualification["provider_id"],
        "capability_scope": ["APPLICATION_RUNTIME"],
        "qualification_digest": qualification_digest(qualification),
        "issued_at": "2026-10-06T00:00:00Z",
        "expires_at": "2026-10-07T00:00:00Z",
    }
    attestation = {
        "schema_version": ATTESTATION_SCHEMA,
        "signed_claim": claim,
        "signature_b64": base64.b64encode(private.sign(canonical_json(claim))).decode(),
    }
    return private, authorities, qualification, attestation

class QualificationAuthorityTests(unittest.TestCase):
    def test_current_railway_evidence_cannot_be_qualified(self):
        result = evaluate_attestation(None, QUALIFICATION, REGISTRY, AUTHORITIES)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["reason"], "qualification_evidence_incomplete")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_verified_attestation_only_creates_warden_eligibility(self):
        _, authorities, qualification, attestation = signed_fixture()
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)
        self.assertTrue(result["qualified"])
        self.assertEqual(result["warden_admission_eligibility"], "ELIGIBLE_FOR_WARDEN_EVALUATION")
        self.assertTrue(result["fresh_warden_decision_required_for_execution"])
        self.assertEqual(result["execution_authority"], "NONE")

    def test_wrong_signature_fails_closed(self):
        _, authorities, qualification, attestation = signed_fixture()
        wrong = Ed25519PrivateKey.generate()
        attestation["signature_b64"] = base64.b64encode(wrong.sign(canonical_json(attestation["signed_claim"]))).decode()
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)
        self.assertEqual(result["reason"], "signature_verification_failed")
        self.assertFalse(result["qualified"])

    def test_tampered_digest_is_rejected(self):
        _, authorities, qualification, attestation = signed_fixture()
        attestation["signed_claim"]["qualification_digest"] = "sha256:" + ("0" * 64)
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)
        self.assertEqual(result["reason"], "qualification_digest_mismatch")

    def test_provider_binding_mismatch_is_rejected(self):
        _, authorities, qualification, attestation = signed_fixture()
        attestation["signed_claim"]["provider_id"] = "OTHER"
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)
        self.assertEqual(result["reason"], "provider_binding_mismatch")

    def test_invalid_capability_type_is_rejected_without_typeerror(self):
        _, authorities, qualification, attestation = signed_fixture()
        attestation["signed_claim"]["capability_scope"] = [{"bad": "id"}]
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)
        self.assertEqual(result["reason"], "invalid_capability_scope")

    def test_expired_and_future_attestations_are_rejected(self):
        _, authorities, qualification, attestation = signed_fixture()
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities,
                                      now=datetime(2026, 10, 8, tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "attestation_expired")
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities,
                                      now=datetime(2026, 10, 5, tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "attestation_not_yet_valid")

    def test_unknown_and_suspended_authority_are_rejected(self):
        _, authorities, qualification, attestation = signed_fixture()
        unknown = copy.deepcopy(attestation)
        unknown["signed_claim"]["authority_id"] = "UNKNOWN"
        self.assertEqual(evaluate_attestation(unknown, qualification, REGISTRY, authorities, now=NOW)["reason"],
                         "unknown_qualification_authority")
        authorities["authorities"][0]["state"] = "SUSPENDED"
        self.assertEqual(evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)["reason"],
                         "qualification_authority_not_active")

    def test_missing_qualification_id_is_rejected(self):
        _, authorities, qualification, attestation = signed_fixture()
        qualification.pop("qualification_id")
        attestation["signed_claim"].pop("qualification_id")
        attestation["signed_claim"]["qualification_digest"] = qualification_digest(qualification)
        self.assertEqual(evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)["reason"],
                         "qualification_id_missing")

    def test_registry_state_and_scope_are_validated(self):
        _, authorities, qualification, attestation = signed_fixture()
        authorities["state"] = "SUSPENDED"
        self.assertEqual(evaluate_attestation(attestation, qualification, REGISTRY, authorities, now=NOW)["reason"],
                         "qualification_authority_registry_not_active")
        malformed = copy.deepcopy(authorities)
        malformed["state"] = "ACTIVE"
        malformed["authorities"][0]["scope"]["capabilities"] = [{"bad": "id"}]
        with self.assertRaisesRegex(AuthorityError, "INVALID_AUTHORITY_CAPABILITY_SCOPE"):
            validate_authority_registry(malformed)
