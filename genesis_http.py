import socket
from typing import Callable, Mapping, Tuple

from genesis_capability_registry import load_registry, registry_projection
from genesis_qualification import load_qualification, evaluate_qualification, QualificationError
from genesis_qualification_authority import load_authority_registry, load_attestation, evaluate_attestation, authority_projection, AuthorityError
from genesis_contract import db_target_from_env, service_status
from genesis_warden_admission import load_warden_decision, load_warden_authority_registry, evaluate_warden_admission, provider_pre_admission_check, not_admitted_projection, WardenAdmissionError
from genesis_runtime import runtime_projection

Probe = Callable[[str, int], bool]


def tcp_probe(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def build_response(path: str, env: Mapping[str, str], probe: Probe = tcp_probe) -> Tuple[int, dict]:
    if path in ("/", "/v1/genesis/status"):
        return 200, service_status()

    if path == "/health":
        return 200, {"status": "ok", "service": "genesis"}

    if path == "/v1/genesis/runtime":
        return 200, runtime_projection(env)

    if path == "/v1/genesis/capabilities":
        try:
            registry = load_registry(env)
            return 200, registry_projection(registry, env)
        except (ValueError, OSError) as exc:
            return 503, {"status": "registry_unavailable", "error": str(exc)}

    if path == "/v1/genesis/qualification":
        try:
            return 200, evaluate_qualification(load_qualification(env), load_registry(env, default_path="config/provider_registry.json"))
        except (ValueError, OSError, QualificationError) as exc:
            return 503, {"status": "qualification_unavailable", "error": str(exc)}

    if path == "/v1/genesis/qualification-authority":
        try:
            qualification = load_qualification(env)
            providers = load_registry(env, default_path="config/provider_registry.json")
            authorities = load_authority_registry(env)
            attestation = load_attestation(env)
            return 200, {"authority_registry": authority_projection(authorities), "provider_qualification": evaluate_attestation(attestation, qualification, providers, authorities)}
        except (ValueError, OSError, QualificationError, AuthorityError) as exc:
            return 503, {"status": "qualification_authority_unavailable", "error": str(exc)}

    if path == "/v1/genesis/warden-admission":
        try:
            qualification = load_qualification(env)
            providers = load_registry(env, default_path="config/provider_registry.json")
            authorities = load_authority_registry(env)
            attestation = load_attestation(env)
            qualification_result = evaluate_attestation(attestation, qualification, providers, authorities)
            decision = load_warden_decision(env)
            warden_authorities = load_warden_authority_registry(env)
            provider_id = qualification.get("provider_id")
            provider_ready, provider_reason = provider_pre_admission_check(providers, provider_id, env)
            if not provider_ready:
                return 200, not_admitted_projection(provider_reason)
            capability_scope = (
                decision.get("capability_scope", []) if isinstance(decision, dict)
                else qualification_result.get("capability_scope", [])
            )
            return 200, evaluate_warden_admission(
                decision, qualification_result, provider_id, capability_scope, warden_authorities
            )
        except (ValueError, OSError, QualificationError, AuthorityError, WardenAdmissionError) as exc:
            return 503, {"status": "warden_admission_unavailable", "error": str(exc)}

    if path == "/ready":
        target = db_target_from_env(env)
        if not target.configured:
            return 503, {"status": "not_ready", "database": "not_configured"}
        if probe(target.host, target.port):
            return 200, {
                "status": "ready",
                "database": "reachable",
                "database_provider": target.provider,
                "database_name": target.database,
            }
        return 503, {"status": "not_ready", "database": "unreachable"}

    return 404, {"error": "not_found"}
