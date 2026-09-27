import json
import tempfile
import unittest
from pathlib import Path

from genesis_capability_registry import (
    RegistryError,
    load_registry,
    registry_projection,
    resolve_capability_candidates,
)


def sample_registry():
    return {
        "schema_version": "genesis.capability-registry.r0.3",
        "registry_id": "REG-TEST-001",
        "state": "ACTIVE",
        "providers": [
            {
                "provider_id": "PROVIDER-CLOUD-001",
                "domain": "CLOUD",
                "state": "QUALIFIED",
                "capabilities": ["OBJECT_STORAGE", "COMPUTE"],
                "endpoint_binding_env": "CLOUD_001_URL",
            },
            {
                "provider_id": "PROVIDER-CLOUD-002",
                "domain": "CLOUD",
                "state": "SUSPENDED",
                "capabilities": ["COMPUTE"],
                "endpoint_binding_env": "CLOUD_002_URL",
            },
        ],
    }


class CapabilityRegistryTests(unittest.TestCase):
    def test_projection_exposes_no_endpoint_secret(self):
        p = registry_projection(sample_registry(), {"CLOUD_001_URL": "https://user:secret@example.invalid"})
        self.assertTrue(p["providers"][0]["endpoint_configured"])
        self.assertNotIn("secret", repr(p))
        self.assertEqual(p["execution_authority"], "NONE")
        self.assertEqual(p["route_selection"], "OUT_OF_SCOPE")

    def test_resolution_returns_candidates_not_selected_route(self):
        candidates = resolve_capability_candidates(
            sample_registry(), {"CLOUD_001_URL": "https://cloud.invalid"}, "COMPUTE", "CLOUD"
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].provider_id, "PROVIDER-CLOUD-001")
        self.assertTrue(candidates[0].warden_admission_required)

    def test_suspended_provider_is_not_candidate(self):
        candidates = resolve_capability_candidates(sample_registry(), {}, "COMPUTE")
        self.assertEqual([c.provider_id for c in candidates], ["PROVIDER-CLOUD-001"])

    def test_invalid_domain_fails(self):
        r = sample_registry()
        r["providers"][0]["domain"] = "UNKNOWN"
        with self.assertRaisesRegex(RegistryError, "INVALID_PROVIDER_DOMAIN"):
            registry_projection(r, {})

    def test_file_registry_loads(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "registry.json"
            p.write_text(json.dumps(sample_registry()), encoding="utf-8")
            loaded = load_registry({"GENESIS_PROVIDER_REGISTRY_PATH": str(p)})
            self.assertEqual(loaded["registry_id"], "REG-TEST-001")


if __name__ == "__main__":
    unittest.main()
