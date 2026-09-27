from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class DatabaseTarget:
    provider: str
    host: Optional[str]
    port: int
    database: Optional[str] = None
    source: str = "unconfigured"

    @property
    def configured(self) -> bool:
        return bool(self.host)


@dataclass(frozen=True)
class ServiceBinding:
    name: str
    url: Optional[str]
    required_for_effects: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.url)


def _target_from_url(url: str, source: str) -> DatabaseTarget:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower().split("+", 1)[0]
    if scheme in ("postgres", "postgresql"):
        provider, default_port = "postgresql", 5432
    elif scheme in ("mysql", "mariadb"):
        provider, default_port = "mysql", 3306
    else:
        provider, default_port = scheme or "unknown", parsed.port or 0

    return DatabaseTarget(
        provider=provider,
        host=parsed.hostname,
        port=parsed.port or default_port,
        database=unquote(parsed.path.lstrip("/")) or None,
        source=source,
    )


def db_target_from_env(env: Mapping[str, str]) -> DatabaseTarget:
    if env.get("DATABASE_URL"):
        return _target_from_url(env["DATABASE_URL"], "DATABASE_URL")

    legacy_url = env.get("MYSQL_URL") or env.get("MYSQL_PUBLIC_URL")
    if legacy_url:
        return _target_from_url(legacy_url, "MYSQL_URL")

    host = env.get("MYSQLHOST")
    try:
        port = int(env.get("MYSQLPORT", "3306"))
    except (TypeError, ValueError):
        port = 3306

    return DatabaseTarget(
        provider="mysql",
        host=host,
        port=port,
        database=env.get("MYSQLDATABASE") or env.get("MYSQL_DATABASE"),
        source="MYSQL_COMPONENTS" if host else "unconfigured",
    )


def service_bindings_from_env(env: Mapping[str, str]) -> dict[str, ServiceBinding]:
    return {
        "warden": ServiceBinding("warden", env.get("WARDEN_URL"), required_for_effects=True),
        "river": ServiceBinding("river", env.get("RIVER_URL"), required_for_effects=True),
    }


def provider_effect_admission(env: Mapping[str, str]) -> tuple[bool, str]:
    bindings = service_bindings_from_env(env)
    if not bindings["warden"].configured:
        return False, "warden_not_configured"
    if env.get("WARDEN_EFFECT_ADMISSION", "").upper() not in {"REQUIRED", "ENFORCED"}:
        return False, "warden_effect_admission_not_enforced"
    if not bindings["river"].configured:
        return False, "river_not_configured"
    return True, "governed_effect_path_configured"


def runtime_projection(env: Mapping[str, str]) -> dict:
    db = db_target_from_env(env)
    bindings = service_bindings_from_env(env)
    admitted, reason = provider_effect_admission(env)
    return {
        "schema_version": "genesis.runtime.r0.2",
        "database": {
            "configured": db.configured,
            "provider": db.provider,
            "host": db.host,
            "port": db.port,
            "database": db.database,
            "source": db.source,
        },
        "bindings": {
            name: {
                "configured": binding.configured,
                "required_for_effects": binding.required_for_effects,
            }
            for name, binding in bindings.items()
        },
        "provider_effects": {"admitted": admitted, "reason": reason},
    }
