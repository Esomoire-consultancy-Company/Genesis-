import base64
import copy
import unittest
import json
from pathlib import Path
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from genesis_warden_admission import (
    canonical_json, decision_digest, evaluate_warden_admission, provider_pre_admission_check,
)

NOW = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)

QUALIFIED = {
    "qualified": True,
    "qualification_authority": "AUTH-TEST-001",
    "warden_admission_eligibility": "ELIGIBLE_FOR_WARDEN_EVALUATION",
    "capability_scope": ["APPLICATION_RUNTIME"],
    "execution_authority": "NONE",
}
NOT_QUALIFIED = {
    "qualified": False,
    "warden_admission_eligibility": "NOT_ELIGIBLE",
    "execution_authority": "NONE",
}


def signed_fixture():
    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode()
    authorities = {
        "schema_version": "genesis.warden-authority-registry.r0.7",
        "registry_id": "GENESIS-WARDEN-AUTHORITY-REGISTRY-TEST",
        "state": "ACTIVE",
        "authorities": [{
            "warden_id": "digitalme:test-warden",
            "signer_key_id": "warden-test-key-001",
            "state": "ACTIVE",
            "algorithm": "Ed25519",
            "key_purpose": "WARDEN_DECISION",
            "public_key_b64": public_b64,
            "scope": {
                "providers": ["PROVIDER-RAILWAY-001"],
                "capabilities": ["APPLICATION_RUNTIME"],
            },
        }],
    }
    claim = {
        "signing_domain": "GENESIS/WARDEN/DECISION/v1",
        "warden_id": "digitalme:test-warden",
        "signer_key_id": "warden-test-key-001",
        "decision_id": "WARDEN-DECISION-001",
        "decision": "ALLOW",
        "provider_id": "PROVIDER-RAILWAY-001",
        "capability_scope": ["APPLICATION_RUNTIME"],
        "principal_ref": "digitalme:test-principal",
        "purpose_ref": "workflow:test",
        "policy_ref": "warden:policy:test",
        "qualification_binding": {
            "authority_id": "AUTH-TEST-001",
            "qualification_result_digest": decision_digest(QUALIFIED),
        },
        "issued_at": "2026-10-06T13:00:00Z",
        "expires_at": "2026-10-06T15:00:00Z",
    }
    envelope = {
        "schema_version": "genesis.warden-admission-decision.r0.7",
        "signed_claim": claim,
        "signature_b64": base64.b64encode(private.sign(canonical_json(claim))).decode(),
    }
    return private, authorities, envelope


def evaluate(envelope, authorities, qualification=QUALIFIED, provider_id="PROVIDER-RAILWAY-001",
             capabilities=None, now=NOW):
    return evaluate_warden_admission(
        envelope, qualification, provider_id,
        capabilities or ["APPLICATION_RUNTIME"], authorities, now=now,
    )


class WardenAdmissionTests(unittest.TestCase):
    def test_provider_pre_admission_blocks_suspension_retirement_and_missing_binding(self):
        registry = json.loads(Path("config/provider_registry.json").read_text())
        provider = registry["providers"][0]
        allowed, reason = provider_pre_admission_check(registry, provider["provider_id"], {})
        self.assertTrue(allowed)
        self.assertEqual(reason, "provider_ready_for_warden_evaluation")
        provider["state"] = "SUSPENDED"
        self.assertEqual(provider_pre_admission_check(registry, provider["provider_id"], {}), (False, "provider_suspended"))
        provider["state"] = "RETIRED"
        self.assertEqual(provider_pre_admission_check(registry, provider["provider_id"], {}), (False, "provider_retired"))
        provider["state"] = "REGISTERED"
        provider["endpoint_binding_env"] = "TEST_PROVIDER_URL"
        self.assertEqual(provider_pre_admission_check(registry, provider["provider_id"], {}), (False, "provider_binding_missing"))

    def test_timestamp_overflow_is_invalid_decision(self):
        private, authorities, envelope = signed_fixture()
        envelope["signed_claim"]["issued_at"] = "0001-01-01T00:00:00+23:59"
        envelope["signature_b64"] = base64.b64encode(
            private.sign(canonical_json(envelope["signed_claim"]))
        ).decode()
        result = evaluate(envelope, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "invalid_warden_decision")

    def test_no_decision_is_not_admitted(self):
        _, authorities, _ = signed_fixture()
        result = evaluate(None, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "warden_decision_missing")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_unqualified_provider_never_reaches_admission(self):
        _, authorities, envelope = signed_fixture()
        result = evaluate(envelope, authorities, qualification=NOT_QUALIFIED)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "provider_not_eligible_for_warden_evaluation")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_unsigned_decision_is_rejected(self):
        _, authorities, envelope = signed_fixture()
        result = evaluate(envelope["signed_claim"], authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "invalid_warden_decision")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_wrong_signature_is_rejected(self):
        _, authorities, envelope = signed_fixture()
        wrong = Ed25519PrivateKey.generate()
        envelope["signature_b64"] = base64.b64encode(
            wrong.sign(canonical_json(envelope["signed_claim"]))
        ).decode()
        result = evaluate(envelope, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "signature_verification_failed")

    def test_unknown_and_suspended_warden_keys_are_rejected(self):
        _, authorities, envelope = signed_fixture()
        unknown = copy.deepcopy(envelope)
        unknown["signed_claim"]["signer_key_id"] = "unknown-key"
        result = evaluate(unknown, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "unknown_warden_signing_key")
        authorities["authorities"][0]["state"] = "SUSPENDED"
        result = evaluate(envelope, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "warden_signing_key_not_active")

    def test_wrong_signing_domain_or_key_purpose_is_rejected(self):
        _, authorities, envelope = signed_fixture()
        wrong_domain = copy.deepcopy(envelope)
        wrong_domain["signed_claim"]["signing_domain"] = "OTHER"
        result = evaluate(wrong_domain, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "invalid_signing_domain")
        authorities["authorities"][0]["key_purpose"] = "OTHER"
        result = evaluate(envelope, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "invalid_warden_key_purpose")

    def test_deny_always_wins(self):
        private, authorities, envelope = signed_fixture()
        envelope["signed_claim"]["decision"] = "DENY"
        envelope["signature_b64"] = base64.b64encode(
            private.sign(canonical_json(envelope["signed_claim"]))
        ).decode()
        result = evaluate(envelope, authorities)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "warden_denied")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_valid_signed_allow_is_scoped_admission_not_execution_authority(self):
        _, authorities, envelope = signed_fixture()
        result = evaluate(envelope, authorities)
        self.assertTrue(result["admitted"])
        self.assertEqual(result["admission_state"], "ADMITTED")
        self.assertEqual(result["execution_authority"], "NONE")
        self.assertTrue(result["provider_native_execution_required"])
        self.assertEqual(result["river_evidence_state"], "REQUIRED_PENDING")

    def test_provider_and_capability_mismatch_fail_closed(self):
        _, authorities, envelope = signed_fixture()
        provider_mismatch = evaluate(envelope, authorities, provider_id="OTHER")
        self.assertEqual(provider_mismatch["reason"], "provider_scope_mismatch")
        self.assertFalse(provider_mismatch["admitted"])
        self.assertEqual(provider_mismatch["execution_authority"], "NONE")
        capability_mismatch = evaluate(envelope, authorities, capabilities=["DEPLOYMENT"])
        self.assertEqual(capability_mismatch["reason"], "capability_scope_mismatch")
        self.assertFalse(capability_mismatch["admitted"])
        self.assertEqual(capability_mismatch["execution_authority"], "NONE")

    def test_expired_and_future_decisions_fail_closed(self):
        _, authorities, envelope = signed_fixture()
        expired = evaluate(envelope, authorities, now=datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(expired["reason"], "warden_decision_expired")
        self.assertFalse(expired["admitted"])
        future = evaluate(envelope, authorities, now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(future["reason"], "warden_decision_not_yet_valid")
        self.assertFalse(future["admitted"])

    def test_qualification_binding_mismatch_fails_closed(self):
        private, authorities, envelope = signed_fixture()
        envelope["signed_claim"]["qualification_binding"]["qualification_result_digest"] = "sha256:" + "0" * 64
        envelope["signature_b64"] = base64.b64encode(
            private.sign(canonical_json(envelope["signed_claim"]))
        ).decode()
        result = evaluate(envelope, authorities)
        self.assertEqual(result["reason"], "qualification_binding_mismatch")
        self.assertFalse(result["admitted"])

    def test_malformed_decision_fails_closed(self):
        _, authorities, envelope = signed_fixture()
        envelope["signed_claim"]["capability_scope"] = [{"bad": "value"}]
        result = evaluate(envelope, authorities)
        self.assertEqual(result["reason"], "invalid_warden_decision")
        self.assertFalse(result["admitted"])
        self.assertEqual(result["execution_authority"], "NONE")
