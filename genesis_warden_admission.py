"""Genesis R0.7 signed, fail-closed Warden admission decision contract."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DECISION_SCHEMA = "genesis.warden-admission-decision.r0.7"
AUTHORITY_SCHEMA = "genesis.warden-authority-registry.r0.7"
SIGNING_DOMAIN = "GENESIS/WARDEN/DECISION/v1"
KEY_PURPOSE = "WARDEN_DECISION"


class WardenAdmissionError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decision_digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


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


def _valid_public_key(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) != 32:
            return False
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(raw)
        return True
    except Exception:
        return False


def validate_warden_authority_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != AUTHORITY_SCHEMA:
        raise WardenAdmissionError("INVALID_WARDEN_AUTHORITY_REGISTRY")
    state = registry.get("state")
    if state not in {"ACTIVE", "ACTIVE_EMPTY", "SUSPENDED", "RETIRED"}:
        raise WardenAdmissionError("INVALID_WARDEN_AUTHORITY_REGISTRY_STATE")
    authorities = registry.get("authorities")
    if not isinstance(authorities, list):
        raise WardenAdmissionError("WARDEN_AUTHORITIES_MUST_BE_LIST")
    if state == "ACTIVE_EMPTY" and authorities:
        raise WardenAdmissionError("ACTIVE_EMPTY_WARDEN_REGISTRY_MUST_HAVE_NO_AUTHORITIES")
    seen = set()
    for item in authorities:
        if not isinstance(item, dict):
            raise WardenAdmissionError("INVALID_WARDEN_AUTHORITY")
        warden_id, key_id = item.get("warden_id"), item.get("signer_key_id")
        if not isinstance(warden_id, str) or not warden_id.strip():
            raise WardenAdmissionError("WARDEN_ID_REQUIRED")
        if not isinstance(key_id, str) or not key_id.strip() or key_id in seen:
            raise WardenAdmissionError("WARDEN_SIGNER_KEY_REQUIRED_OR_DUPLICATE")
        seen.add(key_id)
        if item.get("state") not in {"ACTIVE", "SUSPENDED", "RETIRED"}:
            raise WardenAdmissionError("INVALID_WARDEN_SIGNER_STATE")
        if item.get("algorithm") != "Ed25519":
            raise WardenAdmissionError("UNSUPPORTED_WARDEN_SIGNER_ALGORITHM")
        if not isinstance(item.get("key_purpose"), str) or not item["key_purpose"].strip():
            raise WardenAdmissionError("WARDEN_KEY_PURPOSE_REQUIRED")
        if not _valid_public_key(item.get("public_key_b64")):
            raise WardenAdmissionError("INVALID_WARDEN_PUBLIC_KEY")
        scope = item.get("scope")
        if not isinstance(scope, dict):
            raise WardenAdmissionError("WARDEN_AUTHORITY_SCOPE_REQUIRED")
        for field in ("providers", "capabilities"):
            values = scope.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise WardenAdmissionError("INVALID_WARDEN_AUTHORITY_SCOPE")
    return registry


def load_warden_authority_registry(env, default_path="config/warden_authorities.json"):
    path = Path(env.get("GENESIS_WARDEN_AUTHORITY_PATH", default_path))
    return validate_warden_authority_registry(json.loads(path.read_text(encoding="utf-8")))


def validate_warden_decision(envelope):
    if not isinstance(envelope, dict) or envelope.get("schema_version") != DECISION_SCHEMA:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    claim, signature = envelope.get("signed_claim"), envelope.get("signature_b64")
    if not isinstance(claim, dict) or not isinstance(signature, str) or not signature:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    for field in (
        "signing_domain", "warden_id", "signer_key_id", "decision_id", "provider_id",
        "principal_ref", "purpose_ref", "policy_ref",
    ):
        if not isinstance(claim.get(field), str) or not claim[field].strip():
            raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    if claim.get("decision") not in {"ALLOW", "DENY"}:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    capabilities = claim.get("capability_scope")
    if not isinstance(capabilities, list) or not capabilities or any(
        not isinstance(value, str) or not value.strip() for value in capabilities
    ):
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    binding = claim.get("qualification_binding")
    if not isinstance(binding, dict):
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    if not isinstance(binding.get("authority_id"), str) or not binding["authority_id"].strip():
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    digest = binding.get("qualification_result_digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    issued = _parse_time(claim.get("issued_at"))
    expires = _parse_time(claim.get("expires_at"))
    if expires <= issued:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION_WINDOW")
    for field in ("estate_ref", "room_ref"):
        if field in claim and (not isinstance(claim[field], str) or not claim[field].strip()):
            raise WardenAdmissionError("INVALID_WARDEN_DECISION")
    try:
        base64.b64decode(signature, validate=True)
    except Exception as exc:
        raise WardenAdmissionError("INVALID_WARDEN_DECISION") from exc
    return envelope


def load_warden_decision(env, default_path="config/warden_admission_decision.json"):
    path = Path(env.get("GENESIS_WARDEN_DECISION_PATH", default_path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if value is None:
        return None
    return value


def _verify_ed25519(public_key_b64, signature_b64, payload):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(base64.b64decode(signature_b64, validate=True), payload)
        return True
    except Exception:
        return False


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


def _scope_allows(allowed, requested):
    return "*" in allowed or set(requested).issubset(set(allowed))


def evaluate_warden_admission(
    envelope, qualification_result, provider_id, capability_scope, authority_registry, now=None
):
    if envelope is None:
        if not isinstance(qualification_result, dict) or not qualification_result.get("qualified"):
            return _base("provider_not_eligible_for_warden_evaluation")
        return _base("warden_decision_missing")
    try:
        validate_warden_decision(envelope)
    except WardenAdmissionError:
        return _base("invalid_warden_decision")

    if not isinstance(qualification_result, dict) or not qualification_result.get("qualified"):
        return _base("provider_not_eligible_for_warden_evaluation")
    if qualification_result.get("warden_admission_eligibility") != "ELIGIBLE_FOR_WARDEN_EVALUATION":
        return _base("provider_not_eligible_for_warden_evaluation")

    validate_warden_authority_registry(authority_registry)
    if authority_registry.get("state") != "ACTIVE":
        return _base("warden_authority_registry_not_active")

    claim = envelope["signed_claim"]
    if claim["signing_domain"] != SIGNING_DOMAIN:
        return _base("invalid_signing_domain")
    signer = next(
        (
            item for item in authority_registry["authorities"]
            if item["signer_key_id"] == claim["signer_key_id"] and item["warden_id"] == claim["warden_id"]
        ),
        None,
    )
    if signer is None:
        return _base("unknown_warden_signing_key")
    if signer["state"] != "ACTIVE":
        return _base("warden_signing_key_not_active")
    if signer["key_purpose"] != KEY_PURPOSE:
        return _base("invalid_warden_key_purpose")
    if not _verify_ed25519(signer["public_key_b64"], envelope["signature_b64"], canonical_json(claim)):
        return _base("signature_verification_failed")

    if claim["provider_id"] != provider_id:
        return _base("provider_scope_mismatch")
    requested = capability_scope
    if not isinstance(requested, list) or not requested or any(
        not isinstance(value, str) or not value.strip() for value in requested
    ):
        return _base("capability_scope_mismatch")
    if not set(requested).issubset(set(claim["capability_scope"])):
        return _base("capability_scope_mismatch")
    if not set(requested).issubset(set(qualification_result.get("capability_scope", []))):
        return _base("capability_not_qualified")
    if not _scope_allows(signer["scope"]["providers"], [provider_id]):
        return _base("warden_provider_authority_out_of_scope")
    if not _scope_allows(signer["scope"]["capabilities"], requested):
        return _base("warden_capability_authority_out_of_scope")

    binding = claim["qualification_binding"]
    if binding["authority_id"] != qualification_result.get("qualification_authority"):
        return _base("qualification_binding_mismatch")
    if binding["qualification_result_digest"] != decision_digest(qualification_result):
        return _base("qualification_binding_mismatch")

    issued, expires = _parse_time(claim["issued_at"]), _parse_time(claim["expires_at"])
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise WardenAdmissionError("NOW_MUST_BE_OFFSET_AWARE")
    current = current.astimezone(timezone.utc)
    if current < issued:
        return _base("warden_decision_not_yet_valid")
    if current >= expires:
        return _base("warden_decision_expired")
    if claim["decision"] == "DENY":
        return _base("warden_denied")

    return {
        **_base("warden_allowed_scoped_admission"),
        "admitted": True,
        "admission_state": "ADMITTED",
        "decision_id": claim["decision_id"],
        "warden_id": claim["warden_id"],
        "signer_key_id": claim["signer_key_id"],
        "provider_id": provider_id,
        "capability_scope": list(requested),
        "principal_ref": claim["principal_ref"],
        "purpose_ref": claim["purpose_ref"],
        "policy_ref": claim["policy_ref"],
        "estate_ref": claim.get("estate_ref"),
        "room_ref": claim.get("room_ref"),
        "valid_until": claim["expires_at"],
    }
