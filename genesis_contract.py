from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class DatabaseTarget:
    host: Optional[str]
    port: int = 3306
    database: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.host)


def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.1.0",
        "phase": "bootstrap",
        "capabilities": ["registry", "health", "readiness"],
    }


def db_target_from_env(env: Mapping[str, str]) -> DatabaseTarget:
    url = env.get("MYSQL_URL") or env.get("MYSQL_PUBLIC_URL")
    if url:
        parsed = urlparse(url)
        database = unquote(parsed.path.lstrip("/")) or None
        return DatabaseTarget(
            host=parsed.hostname,
            port=parsed.port or 3306,
            database=database,
        )

    host = env.get("MYSQLHOST")
    port_raw = env.get("MYSQLPORT", "3306")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 3306

    return DatabaseTarget(
        host=host,
        port=port,
        database=env.get("MYSQLDATABASE") or env.get("MYSQL_DATABASE"),
    )
