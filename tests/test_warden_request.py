import base64
import copy
import unittest
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from genesis_warden_request import canonical_json, request_digest, evaluate_warden_request

NOW = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)

def fixture():
    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode()
    principals = {
        "schema_version": "genesis.principal-authority-registry.r0.8",
        "registry_id": "GENESIS-PRINCIPAL-AUTHORITY-REGISTRY-TEST",
        "state": "ACTIVE",
        "authorities": [{
            "principal_ref": "digitalme:test-principal",
            "signer_key_id": "digitalme-test-key-001",
            "state": "ACTIVE",
            "algorithm": "Ed25519",
            "key_purpose": "WARDEN_REQUEST",
            "public_key_b64": public_b64,
            "scope": {"capabilities": ["APPLICATION_RUNTIME"], "purposes": ["workflow:test"]},
        }],
    }
    claim = {
        "signing_domain": "GENESIS/WARDEN/REQUEST/v1",
        "request_id": "REQ-001",
        "nonce": "NONCE-001",
        "idempotency_key": "IDEMP-001",
        "correlation_id": "CORR-001",
        "signer_key_id": "digitalme-test-key-001",
        "capability_id": "APPLICATION_RUNTIME",
        "requested_effect": "RUN_APPLICATION",
        "purpose_ref": "workflow:test",
        "constraints": {"jurisdiction": "IN", "max_effect": "APPLICATION_RUNTIME"},
        "evidence_required": ["PROVIDER_RECEIPT", "RIVER_OBSERVATION"],
        "issued_at": "2026-10-06T23:55:00Z",
        "expires_at": "2026-10-07T00:05:00Z",
    }
    envelope = {
        "schema_version": "genesis.warden-evaluation-request.r0.8",
        "signed_claim": claim,
        "signature_b64": base64.b64encode(private.sign(canonical_json(claim))).decode(),
    }
    registry = {
        "schema_version": "genesis.capability-registry.r0.4",
        "registry_id": "REG-TEST", "state": "ACTIVE",
        "providers": [{
            "provider_id": "P1", "provider_name": "Provider One", "domain": "CLOUD",
            "state": "REGISTERED", "capabilities": ["APPLICATION_RUNTIME"],
            "endpoint_binding_env": None, "credential_posture": "PROVIDER_NATIVE_ONLY",
            "provenance": {"source_kind": "VERIFIED", "source_system": "TEST",
                           "observed_at": "2026-10-06T00:00:00Z", "evidence_refs": ["test:evidence"]},
            "dependency": {"criticality": "LOW", "substitutability": "HIGH",
                           "portability": "TEST", "concentration_scope": "TEST"},
            "exit": {"strategy": "TEST"}, "warden_admission_ref": None,
        }],
    }
    return private, principals, envelope, registry

class WardenRequestTests(unittest.TestCase):
    def test_valid_request_is_provider_neutral_and_non_executing(self):
        _, principals, envelope, registry = fixture()
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertTrue(result["request_validated"])
        self.assertEqual(result["request_state"], "VALIDATED_NOT_DISPATCHED")
        self.assertEqual(result["candidate_count"], 1)
        self.assertNotIn("provider_id", result)
        self.assertIsNone(result["selected_provider"])
        self.assertFalse(result["admitted"])
        self.assertEqual(result["execution_authority"], "NONE")
        self.assertEqual(result["dispatch_authority"], "NONE")
        self.assertEqual(result["forwarding_state"], "NOT_DISPATCHED")
        self.assertTrue(result["warden_evaluation_required"])
        self.assertEqual(result["replay_protection"], "REQUIRED_AT_WARDEN_INGRESS")
        self.assertEqual(result["intent_ref"], "warden-request:REQ-001")
        self.assertEqual(result["idempotency_key"], "IDEMP-001")
        self.assertEqual(result["correlation_id"], "CORR-001")
        self.assertEqual(result["principal_ref"], "digitalme:test-principal")
        self.assertEqual(result["request_digest"], request_digest(envelope["signed_claim"]))

    def test_replay_and_correlation_fields_are_required(self):
        private, principals, envelope, registry = fixture()
        for field in ("nonce", "idempotency_key", "correlation_id"):
            broken = copy.deepcopy(envelope)
            broken["signed_claim"].pop(field)
            broken["signature_b64"] = base64.b64encode(private.sign(canonical_json(broken["signed_claim"]))).decode()
            result = evaluate_warden_request(broken, principals, registry, {}, now=NOW)
            self.assertFalse(result["request_validated"], field)
            self.assertEqual(result["reason"], "invalid_warden_request", field)

    def test_unsigned_outer_envelope_metadata_is_rejected(self):
        _, principals, envelope, registry = fixture()
        envelope["provider_id"] = "P1"
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertFalse(result["request_validated"])
         self.assertEqual(result["reason"], "invalid_warden_request")

    def test_whitespace_replay_identifiers_are_rejected(self):
        private, principals, envelope, registry = fixture()
        for field in ("nonce", "idempotency_key", "correlation_id"):
            broken = copy.deepcopy(envelope)
            broken["signed_claim"][field] = "   "
            broken["signature_b64"] = base64.b64encode(private.sign(canonical_json(broken["signed_claim"]))).decode()
            result = evaluate_warden_request(broken, principals, registry, {}, now=NOW)
            self.assertEqual(result["reason"], "invalid_warden_request", field)

    def test_request_cannot_assert_provider_warden_principal_or_authority(self):
        private, principals, envelope, registry = fixture()
        forbidden = (
            ("provider_id", "P1"),
            ("target_warden_ref", "warden:test"),
            ("principal_ref", "digitalme:claimed"),
            ("authority_ref", "authority:claimed"),
            ("warden_decision_ref", "decision:claimed"),
            ("execution_authorized", True),
            ("admitted", True),
        )
        for field, value in forbidden:
            broken = copy.deepcopy(envelope)
            broken["signed_claim"][field] = value
            broken["signature_b64"] = base64.b64encode(private.sign(canonical_json(broken["signed_claim"]))).decode()
            result = evaluate_warden_request(broken, principals, registry, {}, now=NOW)
            self.assertFalse(result["request_validated"], field)
            self.assertEqual(result["reason"], "caller_authority_or_routing_assertion_not_allowed", field)

    def test_provider_identity_hidden_in_constraints_is_rejected(self):
        private, principals, envelope, registry = fixture()
        envelope["signed_claim"]["constraints"]["provider_id"] = "P1"
        envelope["signature_b64"] = base64.b64encode(private.sign(canonical_json(envelope["signed_claim"]))).decode()
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertEqual(result["reason"], "caller_authority_or_routing_assertion_not_allowed")

    def test_provider_selector_alias_hidden_in_nested_constraints_is_rejected(self):
        private, principals, envelope, registry = fixture()
        envelope["signed_claim"]["constraints"]["ProviderSelector"] = "P1"
        envelope["signature_b64"] = base64.b64encode(private.sign(canonical_json(envelope["signed_claim"]))).decode()
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertEqual(result["reason"], "caller_authority_or_routing_assertion_not_allowed")

    def test_unrecognized_claim_authority_assertions_are_rejected(self):
        private, principals, envelope, registry = fixture()
        envelope["signed_claim"]["principal"] = "digitalme:claimed"
        envelope["signature_b64"] = base64.b64encode(private.sign(canonical_json(envelope["signed_claim"]))).decode()
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertFalse(result["request_validated"])
        self.assertNotEqual(result["request_state"], "VALIDATED_NOT_DISPATCHED")

    def test_malformed_identifier_types_reject_without_projection_error(self):
        _, principals, envelope, registry = fixture()
        envelope["signed_claim"]["request_id"] = 123
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertFalse(result["request_validated"])
       self.assertEqual(result["reason"], "invalid_warden_request")
        self.assertIsNone(result["intent_ref"])

    def test_unsigned_or_bad_signature_fails_closed(self):
        _, principals, envelope, registry = fixture()
        unsigned = evaluate_warden_request(envelope["signed_claim"], principals, registry, {}, now=NOW)
        self.assertEqual(unsigned["reason"], "invalid_warden_request")
        wrong = Ed25519PrivateKey.generate()
        envelope["signature_b64"] = base64.b64encode(wrong.sign(canonical_json(envelope["signed_claim"]))).decode()
        self.assertEqual(evaluate_warden_request(envelope, principals, registry, {}, now=NOW)["reason"],
                         "signature_verification_failed")

    def test_unknown_suspended_or_wrong_scope_principal_fails_closed(self):
        _, principals, envelope, registry = fixture()
        unknown = copy.deepcopy(envelope)
        unknown["signed_claim"]["signer_key_id"] = "unknown"
        self.assertEqual(evaluate_warden_request(unknown, principals, registry, {}, now=NOW)["reason"],
                         "unknown_principal_signing_key")
        principals["authorities"][0]["state"] = "SUSPENDED"
        self.assertEqual(evaluate_warden_request(envelope, principals, registry, {}, now=NOW)["reason"],
                         "principal_signing_key_not_active")
        principals["authorities"][0]["state"] = "ACTIVE"
        principals["authorities"][0]["scope"]["purposes"] = ["other"]
        self.assertEqual(evaluate_warden_request(envelope, principals, registry, {}, now=NOW)["reason"],
                         "principal_purpose_out_of_scope")

    def test_capability_unavailable_fails_closed(self):
        _, principals, envelope, registry = fixture()
        registry["providers"][0]["state"] = "SUSPENDED"
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertEqual(result["reason"], "capability_not_registered_or_active")
        self.assertFalse(result["request_validated"])

    def test_expired_future_and_mutated_requests_fail_closed(self):
        _, principals, envelope, registry = fixture()
        expired = evaluate_warden_request(envelope, principals, registry, {},
            now=datetime(2026,10,7,0,6,tzinfo=timezone.utc))
        self.assertEqual(expired["reason"], "request_expired")
        future = evaluate_warden_request(envelope, principals, registry, {},
            now=datetime(2026,10,6,23,54,tzinfo=timezone.utc))
        self.assertEqual(future["reason"], "request_not_yet_valid")
        envelope["signed_claim"]["requested_effect"] = "DEPLOY_APPLICATION"
        self.assertEqual(evaluate_warden_request(envelope, principals, registry, {}, now=NOW)["reason"],
                         "signature_verification_failed")

    def test_request_digest_is_deterministic_and_material_changes_change_it(self):
        _, _, envelope, _ = fixture()
        first = request_digest(envelope["signed_claim"])
        second = request_digest(copy.deepcopy(envelope["signed_claim"]))
        self.assertEqual(first, second)
        changed = copy.deepcopy(envelope["signed_claim"])
        changed["requested_effect"] = "DEPLOY_APPLICATION"
        self.assertNotEqual(first, request_digest(changed))

    def test_result_never_claims_warden_acceptance_or_execution(self):
        _, principals, envelope, registry = fixture()
        result = evaluate_warden_request(envelope, principals, registry, {}, now=NOW)
        self.assertNotEqual(result["request_state"], "ACCEPTED")
        self.assertNotEqual(result["forwarding_state"], "FORWARDED")
        self.assertIsNone(result["warden_decision_ref"])
        self.assertFalse(result["provider_effects_allowed"])
