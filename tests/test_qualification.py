import copy
import json
import unittest
from pathlib import Path
from genesis_qualification import evaluate_qualification, QualificationError
from genesis_http import build_response
from genesis_capability_registry import registry_projection

REGISTRY = json.loads(Path("config/provider_registry.json").read_text())
RECORD = json.loads(Path("config/railway_qualification.json").read_text())

class QualificationTests(unittest.TestCase):
    def test_railway_is_not_qualified(self):
        result = evaluate_qualification(RECORD, REGISTRY)
        self.assertEqual(result["qualification_profile_results"]["C0"], "PASS")
        self.assertEqual(result["qualification_profile_results"]["C1"], "INCOMPLETE")
        self.assertFalse(result["qualified"])
        self.assertEqual(result["execution_authority"], "NONE")
    def test_unknown_provider_denied(self):
        record = copy.deepcopy(RECORD)
        record["provider_id"] = "UNKNOWN"
        with self.assertRaisesRegex(QualificationError, "UNKNOWN_PROVIDER"):
            evaluate_qualification(record, REGISTRY)
    def test_pass_without_evidence_rejected(self):
        record = copy.deepcopy(RECORD)
        record["checks"]["principal_binding"]["result"] = "PASS"
        with self.assertRaisesRegex(QualificationError, "PASS_WITHOUT_EVIDENCE"):
            evaluate_qualification(record, REGISTRY)
    def test_missing_check_rejected(self):
        record = copy.deepcopy(RECORD)
        del record["checks"]["reconciliation"]
        with self.assertRaisesRegex(QualificationError, "INVALID_OR_MISSING_CHECK"):
            evaluate_qualification(record, REGISTRY)
    def test_all_claimed_passes_do_not_grant_authority(self):
        record = copy.deepcopy(RECORD)
        for item in record["checks"].values():
            item["result"] = "PASS"
            item["evidence_refs"] = ["synthetic:test:untrusted"]
        result = evaluate_qualification(record, REGISTRY)
        self.assertTrue(result["all_profiles_evidenced"])
        self.assertFalse(result["qualified"])
        self.assertEqual(result["qualification_authority"], "NOT_ISSUED")
    def test_registry_still_not_admissible(self):
        projection = registry_projection(REGISTRY, {})
        self.assertEqual(projection["providers"][0]["admission_state"], "NOT_ADMISSIBLE")
    def test_http_read_only(self):
        status, response = build_response("/v1/genesis/qualification", {})
        self.assertEqual(status, 200)
        self.assertFalse(response["qualified"])
    def test_legacy_health(self):
        self.assertEqual(build_response("/health", {})[0], 200)
