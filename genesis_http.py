import socket
from typing import Callable, Mapping, Tuple

from genesis_capability_registry import load_registry, registry_projection
from genesis_contract import db_target_from_env, service_status
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
