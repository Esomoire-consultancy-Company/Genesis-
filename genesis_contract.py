from genesis_runtime import DatabaseTarget, db_target_from_env

def service_status() -> dict:
    return {
        "service": "genesis",
        "version": "0.8.0",
        "phase": "warden-action-request-contract",
        "capabilities": [
            "registry", "health", "readiness", "runtime-projection",
            "provider-binding-resolution", "capability-registry",
            "capability-candidate-resolution", "provider-provenance",
            "dependency-exit-metadata", "warden-admission-projection",
            "provider-qualification-evaluation", "qualification-authority-registry",
            "ed25519-qualification-attestation-verification",
            "warden-qualification-eligibility-projection",
            "warden-admission-decision-evaluation", "scoped-admission-projection",
            "warden-authority-registry", "ed25519-warden-decision-verification",
            "principal-authority-registry", "ed25519-warden-request-verification",
            "provider-neutral-warden-request-validation", "warden-request-http-ingress",
        ],
    }

__all__ = ["DatabaseTarget", "db_target_from_env", "service_status"]
