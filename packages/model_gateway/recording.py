"""Persist sanitized model-call accounting without prompt, media, or response bodies."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from packages.persistence.models import ModelCall

from .resilience import AttemptRecord


class SqlAlchemyModelCallRecorder:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        tool_call_id: UUID,
    ) -> None:
        self._sessions = session_factory
        self._tool_call_id = tool_call_id

    def record(self, attempt: AttemptRecord) -> None:
        usage = attempt.usage
        with self._sessions() as session, session.begin():
            session.add(
                ModelCall(
                    tool_call_id=self._tool_call_id,
                    provider=attempt.provider,
                    model=attempt.model,
                    model_revision=attempt.model_revision,
                    prompt_version=attempt.prompt_version,
                    config_version=attempt.config_version,
                    input_tokens=usage.input_tokens if usage is not None else 0,
                    output_tokens=usage.output_tokens if usage is not None else 0,
                    characters=usage.characters if usage is not None else 0,
                    audio_seconds=usage.audio_seconds if usage is not None else 0.0,
                    cost=usage.cost_usd if usage is not None else None,
                    cost_known=usage is not None and usage.cost_usd is not None,
                    latency_ms=(
                        round(attempt.latency_ms)
                        if attempt.latency_ms is not None
                        else None
                    ),
                    raw_response_ref=attempt.raw_response_ref,
                    status=attempt.status,
                    error_code=attempt.error_code,
                    attempt=attempt.attempt,
                )
            )
