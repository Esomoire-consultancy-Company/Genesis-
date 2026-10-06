import copy
import unittest
from datetime import datetime, timezone

from genesis_warden_admission import evaluate_warden_admission, decision_digest

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

def allow_decision():
    return {
        "schema_version": "genesis.warden-admission-decision.r0.7",
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

class WardenAdmissionTests(unittest.TestCase):
    def test_no_decision_is_not_admitted(self):
        result = evaluate_warden_admission(None, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "warden_decision_missing")
        self.assertEqual(result["execution_authority"], "NONE")

    def test_unqualified_provider_never_reaches_admission(self):
        result = evaluate_warden_admission(allow_decision(), NOT_QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "provider_not_eligible_for_warden_evaluation")

    def test_deny_always_wins(self):
        decision = allow_decision()
        decision["decision"] = "DENY"
        result = evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertFalse(result["admitted"])
        self.assertEqual(result["reason"], "warden_denied")

    def test_valid_allow_is_scoped_admission_not_execution_authority(self):
        result = evaluate_warden_admission(allow_decision(), QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertTrue(result["admitted"])
        self.assertEqual(result["admission_state"], "ADMITTED")
        self.assertEqual(result["execution_authority"], "NONE")
        self.assertTrue(result["provider_native_execution_required"])
        self.assertEqual(result["river_evidence_state"], "REQUIRED_PENDING")

    def test_provider_and_capability_mismatch_fail_closed(self):
        decision = allow_decision()
        self.assertEqual(
            evaluate_warden_admission(decision, QUALIFIED, "OTHER", ["APPLICATION_RUNTIME"], now=NOW)["reason"],
            "provider_scope_mismatch",
        )
        self.assertEqual(
            evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["DEPLOYMENT"], now=NOW)["reason"],
            "capability_scope_mismatch",
        )

    def test_expired_and_future_decisions_fail_closed(self):
        decision = allow_decision()
        expired = evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"],
                                            now=datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(expired["reason"], "warden_decision_expired")
        future = evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"],
                                           now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(future["reason"], "warden_decision_not_yet_valid")

    def test_qualification_binding_mismatch_fails_closed(self):
        decision = allow_decision()
        decision["qualification_binding"]["qualification_result_digest"] = "sha256:" + "0" * 64
        result = evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertEqual(result["reason"], "qualification_binding_mismatch")

    def test_malformed_decision_fails_closed(self):
        decision = allow_decision()
        decision["capability_scope"] = [{"bad": "value"}]
        result = evaluate_warden_admission(decision, QUALIFIED, "PROVIDER-RAILWAY-001", ["APPLICATION_RUNTIME"], now=NOW)
        self.assertEqual(result["reason"], "invalid_warden_decision")
