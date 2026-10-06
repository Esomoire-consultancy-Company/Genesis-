import base64
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from genesis_qualification_authority import ATTESTATION_SCHEMA, canonical_json, evaluate_attestation, qualification_digest

REGISTRY = json.loads(Path("config/provider_registry.json").read_text())
QUALIFICATION = json.loads(Path("config/railway_qualification.json").read_text())
AUTHORITIES = json.loads(Path("config/qualification_authorities.json").read_text())

class QualificationAuthorityTests(unittest.TestCase):
    def test_current_railway_evidence_cannot_be_qualified(self):
        result = evaluate_attestation(None, QUALIFICATION, REGISTRY, AUTHORITIES)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["reason"], "qualification_evidence_incomplete")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_verified_attestation_only_creates_warden_eligibility(self):
        private = Ed25519PrivateKey.generate()
        public_b64 = base64.b64encode(private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)).decode()
        authorities = {"schema_version": "genesis.qualification-authority-registry.r0.6", "registry_id": "TEST",
            "authorities": [{"authority_id": "AUTH-TEST-001", "state": "ACTIVE", "algorithm": "Ed25519",
                "public_key_b64": public_b64, "scope": {"domains": ["CLOUD"], "capabilities": ["APPLICATION_RUNTIME"]}}]}
        qualification = copy.deepcopy(QUALIFICATION)
        for check in qualification["checks"].values():
            check["result"], check["evidence_refs"] = "PASS", ["test:evidence"]
        claim = {"authority_id": "AUTH-TEST-001", "qualification_id": qualification["qualification_id"],
            "provider_id": qualification["provider_id"], "capability_scope": ["APPLICATION_RUNTIME"],
            "qualification_digest": qualification_digest(qualification), "issued_at": "2026-10-06T00:00:00Z",
            "expires_at": "2026-10-07T00:00:00Z"}
        attestation = {"schema_version": ATTESTATION_SCHEMA, "signed_claim": claim,
            "signature_b64": base64.b64encode(private.sign(canonical_json(claim))).decode()}
        result = evaluate_attestation(attestation, qualification, REGISTRY, authorities,
            now=datetime(2026,10,6,12,0,tzinfo=timezone.utc))
        self.assertTrue(result["qualified"])
        self.assertEqual(result["warden_admission_eligibility"], "ELIGIBLE_FOR_WARDEN_EVALUATION")
        self.assertTrue(result["fresh_warden_decision_required_for_execution"])
        self.assertEqual(result["execution_authority"], "NONE")

    def test_tampering_changes_qualification_digest(self):
        self.assertNotEqual(qualification_digest(QUALIFICATION), qualification_digest({**QUALIFICATION, "provider_id": "OTHER"}))
