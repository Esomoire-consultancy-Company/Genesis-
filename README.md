# Genesis Railway Bootstrap

Minimal deployable Genesis service for the Railway production environment.

## Runtime contract

- `GET /` — Genesis bootstrap status
- `GET /v1/genesis/status` — same structured status contract
- `GET /health` — liveness endpoint; does not depend on a datastore
- `GET /ready` — current bootstrap readiness endpoint; checks the configured database target

## Provider-flexible runtime foundation

`requirements.txt` installs a deliberately small interoperability layer:

- SQLAlchemy — provider-neutral SQL access.
- PyMySQL — MySQL/MariaDB driver.
- psycopg[binary] — PostgreSQL driver.
- httpx — HTTP links to Warden, River, provider APIs, and service adapters.
- pydantic + pydantic-settings — typed canonical contracts and environment configuration.
- tenacity — bounded retry/backoff for transient provider failures.
- prometheus-client — operational metrics.
- PyJWT[crypto] — signed bounded tokens/claims when a Warden or federation contract requires them.

This does not make any external provider authoritative by itself. Provider credentials and endpoints stay in Railway variables/secrets and should be admitted through the relevant Warden policy before consequential effects.

## Railway deployment

Railway detects the root `Dockerfile`. Dependencies are installed once during the image build and the runtime launches with `python main.py`. The service binds to `0.0.0.0` and uses Railway's `PORT` environment variable, defaulting to `8080` locally.

The current bootstrap still accepts the existing MySQL environment names for backward compatibility. The R0.2 adapter layer can add a canonical `DATABASE_URL` and HTTP service bindings without replacing those legacy names.

`/health` is the deployment liveness healthcheck. `/ready` is dependency readiness and returns `503` until its required datastore is configured and reachable.

## Local verification

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
PORT=8080 python main.py
```
