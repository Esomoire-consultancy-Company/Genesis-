from genesis_runtime import DatabaseTarget, db_target_from_env


def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.3.0",
        "phase": "capability-registry-bootstrap",
        "capabilities": [
            "registry",
            "health",
            "readiness",
            "runtime-projection",
            "provider-binding-resolution",
            "capability-registry",
            "capability-candidate-resolution",
        ],
    }


__all__ = ["DatabaseTarget", "db_target_from_env", "service_status"]
