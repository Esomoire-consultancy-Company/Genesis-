"""Read-only provider qualification evaluation; never issues Warden authority."""
import json
from pathlib import Path

SCHEMA = "genesis.provider-qualification.r0.5"
PROFILES = ("C0", "C1", "C2", "C3")
REQUIRED = {
    "C0": ("provider_identity", "native_deployment", "health_observation"),
    "C1": ("principal_binding", "context_binding", "denial_receipt"),
    "C2": ("operation_contract", "bounded_authority", "effect_observation"),
    "C3": ("independent_verification", "river_receipt", "reconciliation"),
}
VALID_RESULTS = {"PASS", "FAIL", "NOT_TESTED", "INCONCLUSIVE"}

class QualificationError(ValueError):
    pass

def evaluate_qualification(record, registry):
    if not isinstance(record, dict):
        raise QualificationError("QUALIFICATION_RECORD_MUST_BE_OBJECT")
    if not isinstance(registry, dict) or not isinstance(registry.get("providers"), list):
        raise QualificationError("INVALID_PROVIDER_REGISTRY")
    if record.get("schema_version") != SCHEMA:
        raise QualificationError("INVALID_QUALIFICATION_SCHEMA")
    if not isinstance(record.get("checks"), dict):
        raise QualificationError("CHECKS_REQUIRED")
    ids = {p["provider_id"] for p in registry["providers"]}
    if record.get("provider_id") not in ids:
        raise QualificationError("UNKNOWN_PROVIDER")
    checks = record["checks"]
    for profile in PROFILES:
        for name in REQUIRED[profile]:
            check = checks.get(name)
            if not isinstance(check, dict) or check.get("result") not in VALID_RESULTS:
                raise QualificationError("INVALID_OR_MISSING_CHECK:" + name)
            refs = check.get("evidence_refs")
            if not isinstance(refs, list):
                raise QualificationError("EVIDENCE_REFS_REQUIRED:" + name)
            if check["result"] == "PASS" and (not refs or not all(isinstance(x,str) and x.strip() for x in refs)):
                raise QualificationError("PASS_WITHOUT_EVIDENCE:" + name)
    profile_results = {}
    for profile in PROFILES:
        values = [checks[n]["result"] for n in REQUIRED[profile]]
        profile_results[profile] = (
            "PASS" if all(v == "PASS" for v in values)
            else "FAIL" if "FAIL" in values
            else "INCONCLUSIVE" if "INCONCLUSIVE" in values
            else "INCOMPLETE"
        )
    all_pass = all(v == "PASS" for v in profile_results.values())
    # Evaluation is evidence inventory, not an attestation of source authenticity.
    return {
        "schema_version": SCHEMA,
        "provider_id": record["provider_id"],
        "qualification_profile_results": profile_results,
        "all_profiles_evidenced": all_pass,
        "qualified": False,
        "qualification_authority": "NOT_ISSUED",
        "required_next_gate": "INDEPENDENT_EVIDENCE_VALIDATION_AND_WARDEN_ADMISSION",
        "execution_authority": "NONE",
    }

def load_qualification(env, default_path="config/railway_qualification.json"):
    path = Path(env.get("GENESIS_QUALIFICATION_PATH", default_path))
    return json.loads(path.read_text(encoding="utf-8"))
