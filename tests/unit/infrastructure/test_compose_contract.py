from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_compose_has_pinned_healthy_services_and_named_volumes():
    compose = yaml.safe_load(
        (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert set(services) == {"postgres", "redis", "minio"}
    assert all(
        service["image"] and ":latest" not in service["image"]
        for service in services.values()
    )
    assert all("healthcheck" in service for service in services.values())
    assert set(compose["volumes"]) == {"postgres_data", "redis_data", "minio_data"}
    assert services["postgres"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert services["redis"]["volumes"] == ["redis_data:/data"]
    assert services["minio"]["volumes"] == ["minio_data:/data"]


def test_compose_requires_env_secrets_and_example_contains_only_placeholders():
    compose_text = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for variable in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    ):
        assert f"${{{variable}:?" in compose_text
    values = {
        key: value
        for key, value in (
            line.split("=", 1)
            for line in example.splitlines()
            if line and not line.startswith("#")
        )
    }
    for variable in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "OPENAI_API_KEY",
    ):
        assert values[variable].startswith("replace-with-")
