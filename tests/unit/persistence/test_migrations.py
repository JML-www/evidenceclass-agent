from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from packages.persistence import Base, create_db_engine

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TABLES = {
    "users",
    "workspaces",
    "workspace_members",
    "analysis_jobs",
    "media_assets",
    "agent_runs",
    "agent_steps",
    "tool_calls",
    "model_calls",
    "observations",
    "evidence_items",
    "review_items",
    "artifacts",
    "knowledge_documents",
    "knowledge_chunks",
    "conversations",
    "messages",
    "evaluation_runs",
    "idempotency_records",
}


def _config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/persistence/migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_empty_database_upgrades_downgrades_and_upgrades_again(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "migration cycle.db"
    url = f"sqlite:///{database.as_posix()}"
    config = _config(url)

    command.upgrade(config, "head")
    engine = create_db_engine(url)
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    command.check(config)

    command.downgrade(config, "base")
    assert not (EXPECTED_TABLES & set(inspect(engine).get_table_names()))

    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    engine.dispose()


def test_pgvector_hnsw_index_is_declared_in_model_metadata():
    indexes = {index.name: index for index in Base.metadata.tables["knowledge_chunks"].indexes}
    hnsw = indexes["ix_knowledge_chunks_embedding_hnsw"]

    assert hnsw.dialect_options["postgresql"]["using"] == "hnsw"
    assert hnsw.dialect_options["postgresql"]["ops"] == {
        "embedding": "vector_cosine_ops"
    }
    sql = str(CreateIndex(hnsw).compile(dialect=postgresql.dialect()))
    assert sql == (
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
