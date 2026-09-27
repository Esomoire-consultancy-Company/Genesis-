"""Genesis provider/capability registry.

Genesis records provider identity and advertised capability mappings. It does not
select an execution route and does not turn configuration into authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

ALLOWED_DOMAINS = {"AI", "PAYMENTS", "COMMERCE", "MOBILE", "CLOUD"}
ALLOWED_STATES = {"REGISTERED", "QUALIFIED", "SUSPENDED", "RETIRED"}


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


def validate_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("schema_version") != "genesis.capability-registry.r0.3":
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


def load_registry(env: Mapping[str, str], default_path: str = "/app/config/provider_registry.json") -> dict:
    path = Path(env.get("GENESIS_PROVIDER_REGISTRY_PATH", default_path))
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        registry = {
            "schema_version": "genesis.capability-registry.r0.3",
            "registry_id": "GENESIS-CAPABILITY-REGISTRY-001",
            "state": "ACTIVE_EMPTY",
            "providers": [],
        }
    validate_registry(registry)
    return registry


def registry_projection(registry: Mapping[str, Any], env: Mapping[str, str]) -> dict:
    validate_registry(registry)
    providers = []
    capabilities = set()
    for provider in registry["providers"]:
        capabilities.update(provider["capabilities"])
        binding = provider.get("endpoint_binding_env")
        providers.append({
            "provider_id": provider["provider_id"],
            "domain": provider["domain"],
            "state": provider["state"],
            "capabilities": list(provider["capabilities"]),
            "endpoint_configured": bool(binding and env.get(binding)),
            "warden_admission_required": True,
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
        binding = provider.get("endpoint_binding_env")
        candidates.append(CapabilityCandidate(
            provider_id=provider["provider_id"],
            domain=provider["domain"],
            capability_id=capability_id,
            state=provider["state"],
            endpoint_configured=bool(binding and env.get(binding)),
        ))
    return candidates
