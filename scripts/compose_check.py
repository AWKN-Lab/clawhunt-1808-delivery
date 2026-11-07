"""Static validation of the container path (no Docker daemon required)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures: list[str] = []
    compose_path = ROOT / "docker-compose.yml"
    dockerfile_path = ROOT / "Dockerfile"
    init_path = ROOT / "deploy" / "postgres-init.sql"

    for path in (compose_path, dockerfile_path, init_path):
        if not path.exists():
            failures.append(f"missing {path.relative_to(ROOT)}")
    if failures:
        print("COMPOSE FAIL " + "; ".join(failures))
        return 1

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    for name in ("api", "postgres", "redis"):
        if name not in services:
            failures.append(f"service {name} missing")
    if failures:
        print("COMPOSE FAIL " + "; ".join(failures))
        return 1

    api = services["api"]
    postgres = services["postgres"]
    redis = services["redis"]
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    init_sql = init_path.read_text(encoding="utf-8")

    checks = {
        "api build": api.get("build") == ".",
        "api healthcheck": bool(api.get("healthcheck", {}).get("test")),
        "api waits for postgres": "postgres" in (api.get("depends_on") or {}),
        "api waits for redis": "redis" in (api.get("depends_on") or {}),
        "api postgres mode": (api.get("environment") or {}).get("DB_MODE") == "postgres",
        "pgvector image": "pgvector/pgvector" in str(postgres.get("image", "")),
        "redis image": "redis:7" in str(redis.get("image", "")),
        "postgres healthcheck": bool(postgres.get("healthcheck", {}).get("test")),
        "redis healthcheck": bool(redis.get("healthcheck", {}).get("test")),
        "dockerfile healthcheck": "HEALTHCHECK" in dockerfile,
        "dockerfile python 3.12": "python:3.12" in dockerfile,
        "pgvector extension": "CREATE EXTENSION IF NOT EXISTS vector" in init_sql,
        "embedding table": "kb_chunks_embedding" in init_sql,
    }
    for label, ok in checks.items():
        print(f"{'OK  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(label)

    print(
        "COMPOSE STATIC PASS"
        if not failures
        else "COMPOSE STATIC FAIL " + "; ".join(failures)
    )
    print("note: static validation only; `docker compose up` was not run on this machine")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
