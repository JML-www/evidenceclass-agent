from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_compose_has_pinned_healthy_services_and_named_volumes():
    compose = yaml.safe_load(
        (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert set(services) == {"postgres", "redis", "minio", "prometheus", "grafana"}
    assert all(
        service["image"] and ":latest" not in service["image"]
        for service in services.values()
    )
    assert all("healthcheck" in service for service in services.values())
    assert set(compose["volumes"]) == {
        "postgres_data",
        "redis_data",
        "minio_data",
        "prometheus_data",
        "grafana_data",
    }
    assert services["postgres"]["volumes"] == ["postgres_data:/var/lib/postgresql/data"]
    assert services["postgres"]["image"] == "pgvector/pgvector:0.8.6-pg16-bookworm"
    assert services["redis"]["volumes"] == ["redis_data:/data"]
    assert services["minio"]["volumes"] == ["minio_data:/data"]


def test_observability_stack_is_pinned_and_waits_for_prometheus():
    """Phase-12 Prometheus/Grafana are part of the compose contract, not extras."""

    compose = yaml.safe_load(
        (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    prometheus = services["prometheus"]
    grafana = services["grafana"]
    assert prometheus["image"] == "prom/prometheus:v2.53.0"
    assert grafana["image"] == "grafana/grafana:11.1.0"
    # Grafana must not come up before Prometheus can be scraped, or the
    # provisioned datasource resolves to an unreachable target on first boot.
    assert grafana["depends_on"] == {"prometheus": {"condition": "service_healthy"}}
    assert prometheus["volumes"] == [
        "./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
        "prometheus_data:/prometheus",
    ]
    assert grafana["volumes"] == [
        "./grafana/provisioning:/etc/grafana/provisioning:ro",
        "./grafana/dashboards:/etc/grafana/dashboards:ro",
        "grafana_data:/var/lib/grafana",
    ]
    assert (ROOT / "deploy" / "prometheus" / "prometheus.yml").is_file()
    provisioning = ROOT / "deploy" / "grafana" / "provisioning"
    assert (provisioning / "datasources").is_dir()
    assert (provisioning / "dashboards").is_dir()
    assert (ROOT / "deploy" / "grafana" / "dashboards").is_dir()


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


def test_ci_runs_infrastructure_and_pgvector_as_separate_diagnostic_steps():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "python.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["phase-3-infrastructure"]
    steps = {step["name"]: step.get("run") for step in job["steps"]}

    assert job["services"]["postgres"]["image"] == (
        "pgvector/pgvector:0.8.6-pg16-bookworm"
    )
    assert job["env"]["RUN_STAGE3_INFRA_TESTS"] == "1"
    assert job["env"]["RUN_STAGE6_PGVECTOR_TESTS"] == "1"
    assert steps["Run phase-3 infrastructure integration test"] == (
        "python -m pytest tests/integration/test_stage3_infrastructure.py -q"
    )
    assert steps["Run phase-6 pgvector integration test"] == (
        "python -m pytest tests/integration/test_stage6_pgvector.py -q"
    )
