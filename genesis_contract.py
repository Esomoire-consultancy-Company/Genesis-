from genesis_runtime import DatabaseTarget, db_target_from_env


def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.4.0",
        "phase": "provider-admission-bootstrap",
        "capabilities": [
            "registry",
            "health",
            "readiness",
            "runtime-projection",
            "provider-binding-resolution",
            "capability-registry",
            "capability-candidate-resolution",
            "provider-provenance",
            "dependency-exit-metadata",
            "warden-admission-projection",
        ],
    }


__all__ = ["DatabaseTarget", "db_target_from_env", "service_status"]
