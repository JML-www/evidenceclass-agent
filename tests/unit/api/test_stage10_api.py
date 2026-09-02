from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import (
    Conversation,
    EvidenceItem,
    KnowledgeChunk,
    KnowledgeDocument,
    User,
    Workspace,
    WorkspaceMember,
)


def _client(tmp_path):
    database = tmp_path / "stage10-api.db"
    url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id, job_id = uuid4(), uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(id=user_id, email="stage10@example.test", password_hash=hash_password("password"))
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="stage10", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
        from packages.persistence.models import AnalysisJob

        session.add(
            AnalysisJob(
                id=job_id, workspace_id=workspace_id, mode="video", status="SUCCEEDED"
            )
        )
        session.flush()
        session.add(
            EvidenceItem(
                job_id=job_id,
                evidence_id="EV-10",
                source_ref="camera-a/frame-10",
                fact="student looked toward the board",
                limitations=["observable only"],
            )
        )
    app = create_app(
        AppSettings(database_url=url, auth_secret="stage10-secret", create_schema=False),
        session_factory=sessions,
        object_store=InMemoryObjectStore(),
    )
    return TestClient(app), sessions, engine, workspace_id, job_id


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "stage10@example.test", "password": "password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_evidence_first_answer_summary_and_unavailable_fallback(tmp_path):
    client, sessions, engine, _workspace_id, job_id = _client(tmp_path)
    headers = _headers(client)
    created = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "stage ten", "job_id": str(job_id)},
    )
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]

    answer = client.post(
        f"/api/v1/conversations/{conversation_id}/ask",
        headers=headers,
        json={"content": "what was observed?"},
    )
    assert answer.status_code == 200
    body = answer.json()
    assert body["evidence_available"] is True
    assert body["source"] == "deterministic/mock"
    assert body["citations"][0]["evidence_id"] == "EV-10"
    assert body["boundary"]["job_id"] == str(job_id)
    assert body["summary_version"] == 1

    messages = client.get(
        f"/api/v1/conversations/{conversation_id}/messages", headers=headers
    )
    assert [row["role"] for row in messages.json()] == ["user", "assistant"]
    summary = client.get(
        f"/api/v1/conversations/{conversation_id}/summary", headers=headers
    )
    assert summary.status_code == 200
    assert summary.json()["version"] == 1
    assert summary.json()["summary_hash"]

    second = client.post(
        f"/api/v1/conversations/{conversation_id}/ask",
        headers=headers,
        json={"content": "C:\\private\\lesson.mp4 联系 me@example.test"},
    )
    assert second.status_code == 200
    with sessions() as session:
        conversation = session.get(Conversation, UUID(conversation_id))
        assert conversation is not None
        assert "private\\lesson.mp4" not in str(conversation.summary_json)
        assert "me@example.test" not in str(conversation.summary_json)
        assert conversation.summary_json["citation_ids"] == ["EV-10"]

    empty = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "no evidence"},
    ).json()
    fallback = client.post(
        f"/api/v1/conversations/{empty['conversation_id']}/ask",
        headers=headers,
        json={"content": "can you infer a score?"},
    )
    assert fallback.status_code == 200
    assert fallback.json()["evidence_available"] is False
    assert "证据不足" in fallback.json()["answer"]
    engine.dispose()


def test_authorized_knowledge_is_scoped_and_citable(tmp_path):
    client, sessions, engine, workspace_id, _job_id = _client(tmp_path)
    headers = _headers(client)
    content = "Use observable evidence and state limitations."
    digest = hashlib.sha256(content.encode()).hexdigest()
    document_id = uuid4()
    with sessions() as session, session.begin():
        session.add(
            KnowledgeDocument(
                id=document_id,
                workspace_id=workspace_id,
                source_id="rubric-1",
                source="https://example.test/rubric",
                title="Authorized rubric",
                author_or_organization="Example",
                license="CC-BY",
                authorization_status="AUTHORIZED",
                sha256="a" * 64,
                visibility_scope="workspace",
                version="1.0",
                status="PUBLISHED",
            )
        )
        session.flush()
        session.add(
            KnowledgeChunk(
                document_id=document_id,
                chunk_id="chunk-rubric-1",
                page=2,
                heading="Evidence",
                ordinal=1,
                content=content,
                content_sha256=digest,
                token_count=7,
                metadata_json={},
            )
        )
    conversation = client.post(
        "/api/v1/conversations", headers=headers, json={"title": "knowledge scoped"}
    ).json()
    answer = client.post(
        f"/api/v1/conversations/{conversation['conversation_id']}/ask",
        headers=headers,
        json={"content": "What does the rubric require?"},
    )
    assert answer.status_code == 200
    assert answer.json()["citations"][0]["citation_id"] == "chunk-rubric-1"
    assert answer.json()["citations"][0]["page"] == 2
    engine.dispose()


def test_stage10_openapi_contract(tmp_path):
    client, _sessions, engine, _workspace_id, _job_id = _client(tmp_path)
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    assert {
        "/api/v1/conversations",
        "/api/v1/conversations/{conversation_id}/ask",
        "/api/v1/conversations/{conversation_id}/summary",
        "/api/v1/jobs/{job_id}/feedback",
        "/api/v1/review-items/{review_id}/audit",
    } <= paths
    schemas = spec["components"]["schemas"]
    assert {
        "AnswerResponse",
        "CitationResponse",
        "ConversationSummaryResponse",
        "FeedbackRequest",
    } <= set(schemas)
    engine.dispose()


def test_feedback_audit_stats_and_workspace_boundary(tmp_path):
    client, _sessions, engine, _workspace_id, job_id = _client(tmp_path)
    headers = _headers(client)
    feedback = client.post(
        f"/api/v1/jobs/{job_id}/feedback",
        headers=headers,
        json={
            "decision": "MODIFIED",
            "reason": "occlusion corrected after reviewer inspection",
            "original_observation": {"visible": 1},
            "revised_observation": {"visible": 2},
            "evidence_ids": ["EV-10"],
        },
    )
    assert feedback.status_code == 201
    review_id = feedback.json()["review_id"]
    assert feedback.json()["decision"] == "MODIFIED"

    audits = client.get(f"/api/v1/review-items/{review_id}/audit", headers=headers)
    assert audits.status_code == 200
    assert audits.json()[0]["original_observation"]["observation"] == {"visible": 1}
    assert audits.json()[0]["revised_observation"] == {"visible": 2}

    stats = client.get("/api/v1/review-items/stats", headers=headers)
    assert stats.json() == {
        "total": 1,
        "pending": 0,
        "decided": 1,
        "by_decision": {"MODIFIED": 1},
    }

    forbidden = client.post(
        f"/api/v1/jobs/{job_id}/feedback",
        headers={**headers, "X-Workspace-ID": str(uuid4())},
        json={"decision": "APPROVED", "reason": "not allowed"},
    )
    assert forbidden.status_code == 403
    duplicate = client.post(
        f"/api/v1/jobs/{job_id}/feedback",
        headers=headers,
        json={
            "decision": "MODIFIED",
            "reason": "occlusion corrected after reviewer inspection",
            "original_observation": {"visible": 1},
            "revised_observation": {"visible": 2},
            "evidence_ids": ["EV-10"],
        },
    )
    assert duplicate.status_code == 409

    blank_reason = client.post(
        f"/api/v1/jobs/{job_id}/feedback",
        headers=headers,
        json={"decision": "APPROVED", "reason": "   "},
    )
    assert blank_reason.status_code == 422
    invalid_decision = client.post(
        f"/api/v1/jobs/{job_id}/feedback",
        headers=headers,
        json={"decision": "MAYBE", "reason": "not a supported decision"},
    )
    assert invalid_decision.status_code == 422
    engine.dispose()


def test_conversation_scope_does_not_leak_other_job_or_workspace(tmp_path):
    client, sessions, engine, workspace_id, job_id = _client(tmp_path)
    headers = _headers(client)
    from packages.persistence.models import AnalysisJob

    other_job = uuid4()
    with sessions() as session, session.begin():
        session.add(
            AnalysisJob(
                id=other_job, workspace_id=workspace_id, mode="image", status="SUCCEEDED"
            )
        )
        session.add(
            EvidenceItem(
                job_id=other_job,
                evidence_id="EV-OTHER",
                source_ref="other",
                fact="other job fact",
            )
        )

    created = client.post(
        "/api/v1/conversations", headers=headers, json={"title": "scoped", "job_id": str(job_id)}
    )
    assert created.status_code == 201
    conversation_id = created.json()["conversation_id"]
    answer = client.post(
        f"/api/v1/conversations/{conversation_id}/ask",
        headers=headers,
        json={"content": "show available evidence"},
    )
    assert answer.status_code == 200
    assert {item["evidence_id"] for item in answer.json()["citations"]} == {"EV-10"}
    cross_task_question = client.post(
        f"/api/v1/conversations/{conversation_id}/ask",
        headers=headers,
        json={"content": "请比较 job_other 的结果"},
    )
    assert cross_task_question.status_code == 200
    assert cross_task_question.json()["evidence_available"] is False
    assert "会话边界" in cross_task_question.json()["answer"]
    foreign = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers={**headers, "X-Workspace-ID": str(uuid4())},
    )
    assert foreign.status_code == 403
    engine.dispose()
