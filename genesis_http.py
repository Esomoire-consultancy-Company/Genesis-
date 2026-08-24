import socket
from typing import Callable, Mapping, Tuple

from genesis_contract import db_target_from_env, service_status

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

    if path == "/ready":
        target = db_target_from_env(env)
        if not target.configured:
            return 503, {"status": "not_ready", "database": "not_configured"}
        if probe(target.host, target.port):
            return 200, {
                "status": "ready",
                "database": "reachable",
                "database_name": target.database,
            }
        return 503, {"status": "not_ready", "database": "unreachable"}

    return 404, {"error": "not_found"}
