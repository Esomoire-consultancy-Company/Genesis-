"""Genesis R0.8 provider-neutral, non-authorizing Warden request validation."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from genesis_capability_registry import resolve_capability_candidates

REQUEST_SCHEMA = "genesis.warden-evaluation-request.r0.8"
PRINCIPAL_SCHEMA = "genesis.principal-authority-registry.r0.8"
SIGNING_DOMAIN = "GENESIS/WARDEN/REQUEST/v1"
KEY_PURPOSE = "WARDEN_REQUEST"

FORBIDDEN_CALLER_KEYS = {
    "provider", "provider_id", "provider_name", "provider_ref", "selected_provider",
    "route_ref", "executor_ref", "target_warden_ref", "warden_id", "warden_ref",
    "principal_ref", "principal_id", "authority_ref", "authority_decision_id",
    "decision_ref", "warden_decision_ref", "grant_ref", "consent_ref",
    "allowed", "admitted", "execution_authorized", "authorization_issuer",
}


class WardenRequestError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def request_digest(claim):
    return "sha256:" + hashlib.sha256(canonical_json(claim)).hexdigest()


def _parse_time(value):
    if not isinstance(value, str):
        raise WardenRequestError("INVALID_WARDEN_REQUEST_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise WardenRequestError("WARDEN_REQUEST_TIME_MUST_BE_OFFSET_AWARE")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise WardenRequestError("INVALID_WARDEN_REQUEST_TIME") from exc


def _contains_forbidden_key(value):
    if isinstance(value, dict):
        if FORBIDDEN_CALLER_KEYS.intersection(value):
            return True
        return any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


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


def validate_principal_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != PRINCIPAL_SCHEMA:
        raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_REGISTRY")
    if registry.get("state") not in {"ACTIVE", "ACTIVE_EMPTY", "SUSPENDED", "RETIRED"}:
        raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_REGISTRY_STATE")
    authorities = registry.get("authorities")
    if not isinstance(authorities, list):
        raise WardenRequestError("PRINCIPAL_AUTHORITIES_MUST_BE_LIST")
    if registry["state"] == "ACTIVE_EMPTY" and authorities:
        raise WardenRequestError("ACTIVE_EMPTY_PRINCIPAL_REGISTRY_MUST_HAVE_NO_AUTHORITIES")

    seen = set()
    for authority in authorities:
        if not isinstance(authority, dict):
            raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY")
        principal_ref = authority.get("principal_ref")
        key_id = authority.get("signer_key_id")
        if not isinstance(principal_ref, str) or not principal_ref.strip():
            raise WardenRequestError("PRINCIPAL_REF_REQUIRED")
        if not isinstance(key_id, str) or not key_id.strip() or key_id in seen:
            raise WardenRequestError("PRINCIPAL_SIGNER_KEY_REQUIRED_OR_DUPLICATE")
        seen.add(key_id)
        if authority.get("state") not in {"ACTIVE", "SUSPENDED", "RETIRED"}:
            raise WardenRequestError("INVALID_PRINCIPAL_SIGNER_STATE")
        if authority.get("algorithm") != "Ed25519" or authority.get("key_purpose") != KEY_PURPOSE:
            raise WardenRequestError("INVALID_PRINCIPAL_SIGNER_CONTRACT")
        if not _valid_public_key(authority.get("public_key_b64")):
            raise WardenRequestError("INVALID_PRINCIPAL_PUBLIC_KEY")
        scope = authority.get("scope")
        if not isinstance(scope, dict):
            raise WardenRequestError("PRINCIPAL_AUTHORITY_SCOPE_REQUIRED")
        for field in ("capabilities", "purposes"):
            values = scope.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_SCOPE")
    return registry


def load_principal_authority_registry(env, default_path="config/principal_authorities.json"):
    path = Path(env.get("GENESIS_PRINCIPAL_AUTHORITY_PATH", default_path))
    return validate_principal_registry(json.loads(path.read_text(encoding="utf-8")))


def validate_warden_request(envelope):
    if not isinstance(envelope, dict) or envelope.get("schema_version") != REQUEST_SCHEMA:
        raise WardenRequestError("INVALID_WARDEN_REQUEST")
    claim = envelope.get("signed_claim")
    signature = envelope.get("signature_b64")
    if not isinstance(claim, dict) or not isinstance(signature, str) or not signature:
        raise WardenRequestError("INVALID_WARDEN_REQUEST")
    if _contains_forbidden_key(claim):
        raise WardenRequestError("CALLER_AUTHORITY_OR_ROUTING_ASSERTION_NOT_ALLOWED")

    required = (
        "signing_domain", "request_id", "nonce", "idempotency_key", "correlation_id",
        "signer_key_id", "capability_id", "requested_effect", "purpose_ref",
    )
    if any(not isinstance(claim.get(field), str) or not claim[field].strip() for field in required):
        raise WardenRequestError("INVALID_WARDEN_REQUEST")
    if not isinstance(claim.get("constraints"), dict):
        raise WardenRequestError("INVALID_WARDEN_REQUEST")
    evidence = claim.get("evidence_required")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(value, str) or not value.strip() for value in evidence
    ):
        raise WardenRequestError("INVALID_WARDEN_REQUEST")

    issued = _parse_time(claim.get("issued_at"))
    expires = _parse_time(claim.get("expires_at"))
    if expires <= issued:
        raise WardenRequestError("INVALID_WARDEN_REQUEST_WINDOW")
    try:
        base64.b64decode(signature, validate=True)
    except Exception as exc:
        raise WardenRequestError("INVALID_WARDEN_REQUEST") from exc
    return envelope


def _verify_ed25519(public_key_b64, signature_b64, payload):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64, validate=True))
        key.verify(base64.b64decode(signature_b64, validate=True), payload)
        return True
    except Exception:
        return False


def _scope_allows(values, requested):
    return "*" in values or requested in values


def request_projection(reason, claim=None, principal_ref=None):
    claim = claim if isinstance(claim, dict) else {}
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_validated": False,
        "request_state": "REJECTED",
        "reason": reason,
        "intent_ref": ("warden-request:" + claim["request_id"]) if claim.get("request_id") else None,
        "idempotency_key": claim.get("idempotency_key"),
        "correlation_id": claim.get("correlation_id"),
        "request_digest": request_digest(claim) if claim else None,
        "principal_ref": principal_ref,
        "capability_id": claim.get("capability_id"),
        "requested_effect": claim.get("requested_effect"),
        "purpose_ref": claim.get("purpose_ref"),
        "candidate_count": 0,
        "route_selection": "OUT_OF_SCOPE",
        "selected_provider": None,
        "admitted": False,
        "execution_authority": "NONE",
        "dispatch_authority": "NONE",
        "forwarding_state": "NOT_DISPATCHED",
        "warden_evaluation_required": True,
        "warden_decision_ref": None,
        "provider_effects_allowed": False,
        "provider_native_execution_required": True,
        "river_evidence_state": "REQUIRED_PENDING",
        "replay_protection": "REQUIRED_AT_WARDEN_INGRESS",
        "caller_authority_assertions_accepted": False,
        "caller_routing_assertions_accepted": False,
    }


def evaluate_warden_request(envelope, principal_registry, capability_registry, env, now=None):
    claim = envelope.get("signed_claim") if isinstance(envelope, dict) else None
    try:
        validate_warden_request(envelope)
    except WardenRequestError as exc:
        reason = (
            "caller_authority_or_routing_assertion_not_allowed"
            if str(exc) == "CALLER_AUTHORITY_OR_ROUTING_ASSERTION_NOT_ALLOWED"
            else "invalid_warden_request"
        )
        return request_projection(reason, claim)

    validate_principal_registry(principal_registry)
    if principal_registry["state"] != "ACTIVE":
        return request_projection("principal_authority_registry_not_active", claim)
    if claim["signing_domain"] != SIGNING_DOMAIN:
        return request_projection("invalid_signing_domain", claim)

    signer = next(
        (item for item in principal_registry["authorities"] if item["signer_key_id"] == claim["signer_key_id"]),
        None,
    )
    if signer is None:
        return request_projection("unknown_principal_signing_key", claim)
    principal_ref = signer["principal_ref"]
    if signer["state"] != "ACTIVE":
        return request_projection("principal_signing_key_not_active", claim, principal_ref)
    if not _verify_ed25519(signer["public_key_b64"], envelope["signature_b64"], canonical_json(claim)):
        return request_projection("signature_verification_failed", claim, principal_ref)
    if not _scope_allows(signer["scope"]["capabilities"], claim["capability_id"]):
        return request_projection("principal_capability_out_of_scope", claim, principal_ref)
    if not _scope_allows(signer["scope"]["purposes"], claim["purpose_ref"]):
        return request_projection("principal_purpose_out_of_scope", claim, principal_ref)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise WardenRequestError("NOW_MUST_BE_OFFSET_AWARE")
    current = current.astimezone(timezone.utc)
    if current < _parse_time(claim["issued_at"]):
        return request_projection("request_not_yet_valid", claim, principal_ref)
    if current >= _parse_time(claim["expires_at"]):
        return request_projection("request_expired", claim, principal_ref)

    candidates = resolve_capability_candidates(capability_registry, env, claim["capability_id"])
    if not candidates:
        return request_projection("capability_not_registered_or_active", claim, principal_ref)

    result = request_projection("validated_for_warden_evaluation", claim, principal_ref)
    result.update({
        "request_validated": True,
        "request_state": "VALIDATED_NOT_DISPATCHED",
        "candidate_count": len(candidates),
    })
    return result
