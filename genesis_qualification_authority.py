"""Genesis R0.6 qualification authority and cryptographic attestation verification."""
from __future__ import annotations
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from genesis_qualification import evaluate_qualification

AUTHORITY_SCHEMA = "genesis.qualification-authority-registry.r0.6"
ATTESTATION_SCHEMA = "genesis.provider-qualification-attestation.r0.6"

class AuthorityError(ValueError):
    pass

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def qualification_digest(record):
    return "sha256:" + hashlib.sha256(canonical_json(record)).hexdigest()

def validate_authority_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != AUTHORITY_SCHEMA:
        raise AuthorityError("INVALID_AUTHORITY_REGISTRY")
    authorities = registry.get("authorities")
    if not isinstance(authorities, list):
        raise AuthorityError("AUTHORITIES_MUST_BE_LIST")
    seen = set()
    for item in authorities:
        if not isinstance(item, dict):
            raise AuthorityError("INVALID_AUTHORITY")
        aid = item.get("authority_id")
        if not aid or aid in seen:
            raise AuthorityError("AUTHORITY_ID_REQUIRED_OR_DUPLICATE")
        seen.add(aid)
        if item.get("state") not in {"ACTIVE", "SUSPENDED", "RETIRED"}:
            raise AuthorityError("INVALID_AUTHORITY_STATE")
        if item.get("algorithm") != "Ed25519":
            raise AuthorityError("UNSUPPORTED_AUTHORITY_ALGORITHM")
        if not isinstance(item.get("public_key_b64"), str) or not item["public_key_b64"]:
            raise AuthorityError("AUTHORITY_PUBLIC_KEY_REQUIRED")
        scope = item.get("scope")
        if not isinstance(scope, dict) or not isinstance(scope.get("domains"), list) or not isinstance(scope.get("capabilities"), list):
            raise AuthorityError("AUTHORITY_SCOPE_REQUIRED")
    return registry

def load_authority_registry(env, default_path="config/qualification_authorities.json"):
    path = Path(env.get("GENESIS_QUALIFICATION_AUTHORITY_PATH", default_path))
    return validate_authority_registry(json.loads(path.read_text(encoding="utf-8")))

def load_attestation(env, default_path="config/railway_qualification_attestation.json"):
    path = Path(env.get("GENESIS_QUALIFICATION_ATTESTATION_PATH", default_path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AuthorityError("ATTESTATION_MUST_BE_OBJECT")
    return value

def _parse_time(value):
    if not isinstance(value, str):
        raise AuthorityError("INVALID_ATTESTATION_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorityError("INVALID_ATTESTATION_TIME") from exc
    if parsed.tzinfo is None:
        raise AuthorityError("ATTESTATION_TIME_MUST_BE_OFFSET_AWARE")
    return parsed.astimezone(timezone.utc)

def _verify_ed25519(public_key_b64, signature_b64, payload):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(base64.b64decode(signature_b64, validate=True), payload)
        return True
    except Exception:
        return False

def evaluate_attestation(attestation, qualification, provider_registry, authority_registry, now=None):
    validate_authority_registry(authority_registry)
    evidence = evaluate_qualification(qualification, provider_registry)
    base = {
        "schema_version": ATTESTATION_SCHEMA,
        "qualified": False,
        "qualification_authority": "NOT_ISSUED",
        "warden_admission_eligibility": "NOT_ELIGIBLE",
        "fresh_warden_decision_required_for_execution": True,
        "execution_authority": "NONE",
    }
    if not evidence["all_profiles_evidenced"]:
        return {**base, "reason": "qualification_evidence_incomplete"}
    if attestation is None:
        return {**base, "reason": "attestation_not_issued"}
    if not isinstance(attestation, dict) or attestation.get("schema_version") != ATTESTATION_SCHEMA:
        raise AuthorityError("INVALID_ATTESTATION_SCHEMA")
    claim, signature = attestation.get("signed_claim"), attestation.get("signature_b64")
    if not isinstance(claim, dict) or not isinstance(signature, str) or not signature:
        raise AuthorityError("SIGNED_CLAIM_AND_SIGNATURE_REQUIRED")
    aid = claim.get("authority_id")
    issuer = next((a for a in authority_registry["authorities"] if a["authority_id"] == aid), None)
    if issuer is None:
        return {**base, "reason": "unknown_qualification_authority"}
    base["qualification_authority"] = aid
    if issuer["state"] != "ACTIVE":
        return {**base, "reason": "qualification_authority_not_active"}
    provider_id = qualification.get("provider_id")
    provider = next((p for p in provider_registry.get("providers", []) if p.get("provider_id") == provider_id), None)
    if provider is None or claim.get("provider_id") != provider_id:
        return {**base, "reason": "provider_binding_mismatch"}
    if claim.get("qualification_id") != qualification.get("qualification_id"):
        return {**base, "reason": "qualification_id_mismatch"}
    if claim.get("qualification_digest") != qualification_digest(qualification):
        return {**base, "reason": "qualification_digest_mismatch"}
    capabilities = claim.get("capability_scope")
    if not isinstance(capabilities, list) or not capabilities:
        return {**base, "reason": "capability_scope_required"}
    if provider.get("domain") not in issuer["scope"]["domains"]:
        return {**base, "reason": "authority_domain_out_of_scope"}
    if not set(capabilities).issubset(set(provider.get("capabilities", []))):
        return {**base, "reason": "provider_capability_scope_mismatch"}
    allowed = issuer["scope"]["capabilities"]
    if "*" not in allowed and not set(capabilities).issubset(set(allowed)):
        return {**base, "reason": "authority_capability_out_of_scope"}
    issued, expires = _parse_time(claim.get("issued_at")), _parse_time(claim.get("expires_at"))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise AuthorityError("NOW_MUST_BE_OFFSET_AWARE")
    current = current.astimezone(timezone.utc)
    if expires <= issued:
        return {**base, "reason": "invalid_attestation_window"}
    if current < issued:
        return {**base, "reason": "attestation_not_yet_valid"}
    if current >= expires:
        return {**base, "reason": "attestation_expired"}
    if not _verify_ed25519(issuer["public_key_b64"], signature, canonical_json(claim)):
        return {**base, "reason": "signature_verification_failed"}
    return {**base, "qualified": True, "warden_admission_eligibility": "ELIGIBLE_FOR_WARDEN_EVALUATION",
            "capability_scope": capabilities, "reason": "verified_qualification_attestation"}

def authority_projection(registry):
    validate_authority_registry(registry)
    return {
        "schema_version": registry["schema_version"],
        "registry_id": registry.get("registry_id"),
        "authority_count": len(registry["authorities"]),
        "active_authority_count": sum(1 for a in registry["authorities"] if a["state"] == "ACTIVE"),
        "signature_algorithm": "Ed25519",
        "execution_authority": "NONE",
        "fresh_warden_decision_required_for_execution": True,
    }
