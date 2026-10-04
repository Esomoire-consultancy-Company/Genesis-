from genesis_runtime import DatabaseTarget, db_target_from_env

def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.5.0",
        "phase": "provider-qualification-observation",
        "capabilities": [
            "registry", "health", "readiness", "runtime-projection",
            "provider-binding-resolution", "capability-registry",
            "capability-candidate-resolution", "provider-provenance",
            "dependency-exit-metadata", "warden-admission-projection",
            "provider-qualification-evaluation",
        ],
    }

__all__ = ["DatabaseTarget", "db_target_from_env", "service_status"]
