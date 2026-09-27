"""Genesis provider/capability registry and admission projection.

Genesis records provider identity, capabilities, provenance, dependency posture,
exit posture, and Warden admission references. It never converts registration
or qualification into execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

ALLOWED_DOMAINS = {"AI", "PAYMENTS", "COMMERCE", "MOBILE", "CLOUD"}
ALLOWED_STATES = {"REGISTERED", "QUALIFIED", "SUSPENDED", "RETIRED"}
ALLOWED_SCHEMAS = {
    "genesis.capability-registry.r0.3",
    "genesis.capability-registry.r0.4",
}


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityCandidate:
    provider_id: str
    domain: str
    capability_id: str
    state: str
    endpoint_configured: bool
    warden_admission_required: bool = True
    warden_admission_ref: str | None = None


def _validate_r04_provider(provider: Mapping[str, Any]) -> None:
    if not provider.get("provider_name"):
        raise RegistryError("PROVIDER_NAME_REQUIRED")
    if provider.get("credential_posture") != "PROVIDER_NATIVE_ONLY":
        raise RegistryError("PROVIDER_NATIVE_CREDENTIAL_POSTURE_REQUIRED")

    provenance = provider.get("provenance")
    if not isinstance(provenance, dict):
        raise RegistryError("PROVENANCE_REQUIRED")
    if provenance.get("source_kind") not in {"PROVIDER_NATIVE", "ATTESTED", "VERIFIED"}:
        raise RegistryError("INVALID_PROVENANCE_SOURCE_KIND")
    if not provenance.get("source_system") or not provenance.get("observed_at"):
        raise RegistryError("PROVENANCE_SOURCE_AND_TIME_REQUIRED")
    refs = provenance.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise RegistryError("PROVENANCE_EVIDENCE_REQUIRED")

    dependency = provider.get("dependency")
    if not isinstance(dependency, dict):
        raise RegistryError("DEPENDENCY_METADATA_REQUIRED")
    for key in ("criticality", "substitutability", "portability", "concentration_scope"):
        if not dependency.get(key):
            raise RegistryError("DEPENDENCY_METADATA_INCOMPLETE")

    exit_meta = provider.get("exit")
    if not isinstance(exit_meta, dict) or not exit_meta.get("strategy"):
        raise RegistryError("EXIT_METADATA_REQUIRED")

    admission = provider.get("warden_admission_ref")
    if admission is not None and (not isinstance(admission, str) or not admission.strip()):
        raise RegistryError("INVALID_WARDEN_ADMISSION_REF")


def validate_registry(registry: Mapping[str, Any]) -> None:
    schema = registry.get("schema_version")
    if schema not in ALLOWED_SCHEMAS:
        raise RegistryError("INVALID_REGISTRY_SCHEMA")
    if not registry.get("registry_id"):
        raise RegistryError("REGISTRY_ID_REQUIRED")
    providers = registry.get("providers")
    if not isinstance(providers, list):
        raise RegistryError("PROVIDERS_MUST_BE_LIST")

    seen = set()
    for provider in providers:
        provider_id = provider.get("provider_id")
        if not provider_id or provider_id in seen:
            raise RegistryError("PROVIDER_ID_REQUIRED_OR_DUPLICATE")
        seen.add(provider_id)
        if provider.get("domain") not in ALLOWED_DOMAINS:
            raise RegistryError("INVALID_PROVIDER_DOMAIN")
        if provider.get("state") not in ALLOWED_STATES:
            raise RegistryError("INVALID_PROVIDER_STATE")
        capabilities = provider.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise RegistryError("PROVIDER_CAPABILITIES_REQUIRED")
        if any(not isinstance(c, str) or not c.strip() for c in capabilities):
            raise RegistryError("INVALID_CAPABILITY_ID")
        binding = provider.get("endpoint_binding_env")
        if binding is not None and (not isinstance(binding, str) or not binding.strip()):
            raise RegistryError("INVALID_ENDPOINT_BINDING")
        if schema == "genesis.capability-registry.r0.4":
            _validate_r04_provider(provider)


def load_registry(env: Mapping[str, str], default_path: str = "/app/config/provider_registry.json") -> dict:
    path = Path(env.get("GENESIS_PROVIDER_REGISTRY_PATH", default_path))
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        registry = {
            "schema_version": "genesis.capability-registry.r0.4",
            "registry_id": "GENESIS-CAPABILITY-REGISTRY-001",
            "state": "ACTIVE_EMPTY",
            "providers": [],
        }
    validate_registry(registry)
    return registry


def _endpoint_configured(provider: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    binding = provider.get("endpoint_binding_env")
    return bool(binding and env.get(binding))


def provider_admission_state(provider: Mapping[str, Any], env: Mapping[str, str]) -> tuple[str, str]:
    if provider["state"] == "SUSPENDED":
        return "BLOCKED", "provider_suspended"
    if provider["state"] == "RETIRED":
        return "BLOCKED", "provider_retired"
    if provider["state"] != "QUALIFIED":
        return "NOT_ADMISSIBLE", "provider_not_qualified"
    if not provider.get("warden_admission_ref"):
        return "NOT_ADMISSIBLE", "warden_admission_missing"
    if provider.get("endpoint_binding_env") and not _endpoint_configured(provider, env):
        return "NOT_ADMISSIBLE", "provider_binding_missing"
    return "ELIGIBLE_FOR_WARDEN_EVALUATION", "fresh_warden_decision_required"


def registry_projection(registry: Mapping[str, Any], env: Mapping[str, str]) -> dict:
    validate_registry(registry)
    providers = []
    capabilities = set()
    for provider in registry["providers"]:
        capabilities.update(provider["capabilities"])
        admission_state, admission_reason = provider_admission_state(provider, env)
        provenance = provider.get("provenance", {})
        dependency = provider.get("dependency", {})
        exit_meta = provider.get("exit", {})
        providers.append({
            "provider_id": provider["provider_id"],
            "provider_name": provider.get("provider_name"),
            "domain": provider["domain"],
            "state": provider["state"],
            "capabilities": list(provider["capabilities"]),
            "endpoint_configured": _endpoint_configured(provider, env),
            "credential_posture": provider.get("credential_posture", "UNSPECIFIED"),
            "provenance": {
                "source_kind": provenance.get("source_kind"),
                "source_system": provenance.get("source_system"),
                "observed_at": provenance.get("observed_at"),
                "evidence_ref_count": len(provenance.get("evidence_refs", [])),
            },
            "dependency": {
                "criticality": dependency.get("criticality"),
                "substitutability": dependency.get("substitutability"),
                "portability": dependency.get("portability"),
                "concentration_scope": dependency.get("concentration_scope"),
            },
            "exit": {"strategy": exit_meta.get("strategy")},
            "warden_admission_registered": bool(provider.get("warden_admission_ref")),
            "admission_state": admission_state,
            "admission_reason": admission_reason,
        })
    return {
        "schema_version": registry["schema_version"],
        "registry_id": registry["registry_id"],
        "state": registry.get("state", "ACTIVE"),
        "provider_count": len(providers),
        "capability_count": len(capabilities),
        "providers": providers,
        "execution_authority": "NONE",
        "route_selection": "OUT_OF_SCOPE",
        "fresh_warden_decision_required_for_execution": True,
    }


def resolve_capability_candidates(
    registry: Mapping[str, Any],
    env: Mapping[str, str],
    capability_id: str,
    domain: str | None = None,
) -> list[CapabilityCandidate]:
    validate_registry(registry)
    if domain is not None and domain not in ALLOWED_DOMAINS:
        raise RegistryError("INVALID_PROVIDER_DOMAIN")

    candidates = []
    for provider in registry["providers"]:
        if provider["state"] not in {"REGISTERED", "QUALIFIED"}:
            continue
        if domain and provider["domain"] != domain:
            continue
        if capability_id not in provider["capabilities"]:
            continue
        candidates.append(CapabilityCandidate(
            provider_id=provider["provider_id"],
            domain=provider["domain"],
            capability_id=capability_id,
            state=provider["state"],
            endpoint_configured=_endpoint_configured(provider, env),
            warden_admission_ref=provider.get("warden_admission_ref"),
        ))
    return candidates
