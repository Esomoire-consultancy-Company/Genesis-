# Genesis Railway Bootstrap

Minimal deployable Genesis service for the Railway production environment.

## Runtime contract

- `GET /` — Genesis bootstrap status
- `GET /v1/genesis/status` — same structured status contract
- `GET /health` — liveness endpoint; does not depend on MySQL
- `GET /ready` — readiness endpoint; checks whether the configured MySQL host is reachable

## Railway deployment

Railway will detect the root `Dockerfile`. The image makes `start.sh` executable and launches `python main.py`. The service binds to `0.0.0.0` and uses Railway's `PORT` environment variable, defaulting to `8080` locally.

For database readiness, configure the Genesis service with a Railway reference variable named `MYSQL_URL` that resolves to the MySQL service's private `MYSQL_URL`. Do not copy database passwords into source control.

`/health` is the appropriate deployment healthcheck. `/ready` is intended for dependency readiness and returns `503` until MySQL is configured and reachable.

## Local verification

```sh
python -m unittest discover -s tests -v
PORT=8080 python main.py
```
