from genesis_runtime import DatabaseTarget, db_target_from_env


def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.2.0",
        "phase": "provider-flexible-bootstrap",
        "capabilities": [
            "registry",
            "health",
            "readiness",
            "runtime-projection",
            "provider-binding-resolution",
        ],
    }


__all__ = ["DatabaseTarget", "db_target_from_env", "service_status"]
