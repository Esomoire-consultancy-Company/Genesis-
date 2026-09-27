import json
import tempfile
import unittest
from pathlib import Path

from genesis_capability_registry import (
    RegistryError,
    load_registry,
    provider_admission_state,
    registry_projection,
    resolve_capability_candidates,
)


def sample_registry(state="QUALIFIED", admission_ref="WD-ADMISSION-TEST-001"):
    return {
        "schema_version": "genesis.capability-registry.r0.4",
        "registry_id": "REG-TEST-001",
        "state": "ACTIVE",
        "providers": [{
            "provider_id": "PROVIDER-CLOUD-001",
            "provider_name": "Example Cloud",
            "domain": "CLOUD",
            "state": state,
            "capabilities": ["OBJECT_STORAGE", "COMPUTE"],
            "endpoint_binding_env": "CLOUD_001_URL",
            "credential_posture": "PROVIDER_NATIVE_ONLY",
            "provenance": {
                "source_kind": "PROVIDER_NATIVE",
                "source_system": "EXAMPLE",
                "observed_at": "2026-09-27T00:00:00Z",
                "evidence_refs": ["provider:example:1"],
            },
            "dependency": {
                "criticality": "HIGH",
                "substitutability": "PARTIAL",
                "portability": "CONTAINER",
                "concentration_scope": "TEST",
            },
            "exit": {"strategy": "REDEPLOY"},
            "warden_admission_ref": admission_ref,
        }],
    }


class CapabilityRegistryTests(unittest.TestCase):
    def test_projection_exposes_no_endpoint_secret_or_raw_evidence_refs(self):
        p = registry_projection(sample_registry(), {"CLOUD_001_URL": "https://user:secret@example.invalid"})
        self.assertTrue(p["providers"][0]["endpoint_configured"])
        self.assertNotIn("secret", repr(p))
        self.assertNotIn("provider:example:1", repr(p))
        self.assertEqual(p["execution_authority"], "NONE")
        self.assertTrue(p["fresh_warden_decision_required_for_execution"])

    def test_registered_provider_is_known_but_not_admissible(self):
        r = sample_registry(state="REGISTERED", admission_ref=None)
        candidates = resolve_capability_candidates(r, {}, "COMPUTE", "CLOUD")
        self.assertEqual(len(candidates), 1)
        state, reason = provider_admission_state(r["providers"][0], {})
        self.assertEqual(state, "NOT_ADMISSIBLE")
        self.assertEqual(reason, "provider_not_qualified")

    def test_qualified_provider_without_admission_is_not_admissible(self):
        r = sample_registry(admission_ref=None)
        state, reason = provider_admission_state(r["providers"][0], {"CLOUD_001_URL": "https://cloud.invalid"})
        self.assertEqual((state, reason), ("NOT_ADMISSIBLE", "warden_admission_missing"))

    def test_qualified_admitted_provider_still_requires_fresh_warden_decision(self):
        r = sample_registry()
        state, reason = provider_admission_state(r["providers"][0], {"CLOUD_001_URL": "https://cloud.invalid"})
        self.assertEqual(state, "ELIGIBLE_FOR_WARDEN_EVALUATION")
        self.assertEqual(reason, "fresh_warden_decision_required")

    def test_missing_binding_blocks_admission_evaluation(self):
        r = sample_registry()
        state, reason = provider_admission_state(r["providers"][0], {})
        self.assertEqual((state, reason), ("NOT_ADMISSIBLE", "provider_binding_missing"))

    def test_suspended_provider_is_not_candidate(self):
        r = sample_registry(state="SUSPENDED")
        self.assertEqual(resolve_capability_candidates(r, {}, "COMPUTE"), [])

    def test_r04_requires_provider_native_credentials(self):
        r = sample_registry()
        r["providers"][0]["credential_posture"] = "COPIED_INTO_GENESIS"
        with self.assertRaisesRegex(RegistryError, "PROVIDER_NATIVE_CREDENTIAL_POSTURE_REQUIRED"):
            registry_projection(r, {})

    def test_r04_requires_provenance_dependency_and_exit(self):
        for field, error in [
            ("provenance", "PROVENANCE_REQUIRED"),
            ("dependency", "DEPENDENCY_METADATA_REQUIRED"),
            ("exit", "EXIT_METADATA_REQUIRED"),
        ]:
            r = sample_registry()
            del r["providers"][0][field]
            with self.assertRaisesRegex(RegistryError, error):
                registry_projection(r, {})

    def test_r03_registry_remains_readable_for_additive_compatibility(self):
        r = {
            "schema_version": "genesis.capability-registry.r0.3",
            "registry_id": "LEGACY-R03",
            "state": "ACTIVE",
            "providers": [{
                "provider_id": "LEGACY-001",
                "domain": "CLOUD",
                "state": "REGISTERED",
                "capabilities": ["COMPUTE"],
                "endpoint_binding_env": None,
            }],
        }
        p = registry_projection(r, {})
        self.assertEqual(p["provider_count"], 1)

    def test_file_registry_loads(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.json"
            p.write_text(json.dumps(sample_registry()), encoding="utf-8")
            loaded = load_registry({"GENESIS_PROVIDER_REGISTRY_PATH": str(p)})
            self.assertEqual(loaded["registry_id"], "REG-TEST-001")


if __name__ == "__main__":
    unittest.main()
