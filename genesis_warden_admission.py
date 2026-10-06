"""Genesis R0.7 fail-closed Warden admission decision contract."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DECISION_SCHEMA = "genesis.warden-admission-decision.r0.7"


class WardenAdmissionError(ValueError):
    pass


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decision_digest(value):
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _parse_time(value):
    if not isinstance(value, str):
        raise WardenAdmissionError("INVALID_WARDEN_DECISION_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION_TIME") from exc
    if parsed.tzinfo is None:
        raise WardenAdmissionError("WARDEN_DECISION_TIME_MUST_BE_OFFSET_AWARE")
    return parsed.astimezone(timezone.utc)


def validate_warden_decision(decision):
    if not isinstance(decision, dict) or decision.get("schema_version") != DECISION_SCHEMA:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    for field in ("decision_id", "provider_id", "principal_ref", "purpose_ref", "policy_ref"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    if decision.get("decision") not in {"ALLOW", "DENY"}:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    capabilities = decision.get("capability_scope")
    if not isinstance(capabilities, list) or not capabilities or any(
        not isinstance(value, str) or not value.strip() for value in capabilities
    ):
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    binding = decision.get("qualification_binding")
    if not isinstance(binding, dict):
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    if not isinstance(binding.get("authority_id"), str) or not binding["authority_id"].strip():
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    digest = binding.get("qualification_result_digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    issued = _parse_time(decision.get("issued_at"))
    expires = _parse_time(decision.get("expires_at"))
    if expires <= issued:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION_WINDOW")
    for field in ("estate_ref", "room_ref"):
        if field in decision and (not isinstance(decision[field], str) or not decision[field].strip()):
            raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    return decision


def load_warden_decision(env, default_path="config/warden_admission_decision.json"):
    path = Path(env.get("GENESIS_WARDEN_DECISION_PATH", default_path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if value is None:
        return None
    return validate_warden_decision(value)


def _base(reason):
    return {
        "schema_version": DECISION_SCHEMA,
        "admitted": False,
        "admission_state": "NOT_ADMITTED",
        "reason": reason,
        "execution_authority": "NONE",
        "provider_native_execution_required": True,
        "river_evidence_state": "REQUIRED_PENDING",
    }


def evaluate_warden_admission(decision, qualification_result, provider_id, capability_scope, now=None):
    if decision is not None:
        try:
            validate_warden_decision(decision)
        except WardenAdmissionError:
            return _base("invalid_warden_decision")

    if not isinstance(qualification_result, dict) or not qualification_result.get("qualified"):
        return _base("provider_not_eligible_for_warden_evaluation")
    if qualification_result.get("warden_admission_eligibility") != "ELIGIBLE_FOR_WARDEN_EVALUATION":
        return _base("provider_not_eligible_for_warden_evaluation")
    if decision is None:
        return _base("warden_decision_missing")

    if decision["provider_id"] != provider_id:
        return _base("provider_scope_mismatch")
    requested = capability_scope
    if not isinstance(requested, list) or not requested or any(not isinstance(v, str) or not v.strip() for v in requested):
        return _base("capability_scope_mismatch")
    if not set(requested).issubset(set(decision["capability_scope"])):
        return _base("capability_scope_mismatch")
    qualified_scope = qualification_result.get("capability_scope", [])
    if not set(requested).issubset(set(qualified_scope)):
        return _base("capability_not_qualified")

    binding = decision["qualification_binding"]
    if binding["authority_id"] != qualification_result.get("qualification_authority"):
        return _base("qualification_binding_mismatch")
    if binding["qualification_result_digest"] != decision_digest(qualification_result):
        return _base("qualification_binding_mismatch")

    issued, expires = _parse_time(decision["issued_at"]), _parse_time(decision["expires_at"])
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise WardenAdmissionError("NOW_MUST_BE_OFFSET_AWARE")
    current = current.astimezone(timezone.utc)
    if current < issued:
        return _base("warden_decision_not_yet_valid")
    if current >= expires:
        return _base("warden_decision_expired")
    if decision["decision"] == "DENY":
        return _base("warden_denied")

    return {
        **_base("warden_allowed_scoped_admission"),
        "admitted": True,
        "admission_state": "ADMITTED",
        "decision_id": decision["decision_id"],
        "provider_id": provider_id,
        "capability_scope": list(requested),
        "principal_ref": decision["principal_ref"],
        "purpose_ref": decision["purpose_ref"],
        "policy_ref": decision["policy_ref"],
        "estate_ref": decision.get("estate_ref"),
        "room_ref": decision.get("room_ref"),
        "valid_until": decision["expires_at"],
    }
