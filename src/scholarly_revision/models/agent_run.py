'''Persistent Codex subprocess run metadata and validation decisions.'''

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentRunStatus(str, Enum):
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    COMPLETED_RAW = 'COMPLETED_RAW'
    VALIDATING = 'VALIDATING'
    VALIDATED = 'VALIDATED'
    AUTHOR_REVIEW = 'AUTHOR_REVIEW'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    IMPORTED = 'IMPORTED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    BLOCKED = 'BLOCKED'
    RECOVERY_REQUIRED = 'RECOVERY_REQUIRED'


class AgentAuthorDecision(str, Enum):
    APPROVE_IMPORT = 'APPROVE_IMPORT'
    REJECT_OUTPUT = 'REJECT_OUTPUT'


class AgentRun(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    run_id: str = Field(pattern=r'^RUN-[A-Z0-9-]{8,}$')
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: AgentRunStatus = AgentRunStatus.QUEUED
    progress_percent: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    worker_pid: int | None = Field(default=None, ge=1)
    codex_pid: int | None = Field(default=None, ge=1)
    codex_executable: str | None = None
    codex_version: str | None = None
    prompt_version: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    context_manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    output_schema_name: str = Field(min_length=1)
    structured_mode: str = Field(min_length=1)
    exit_code: int | None = None
    validation_passed: bool | None = None
    validation_error_codes: list[str] = Field(default_factory=list)
    author_decision: AgentAuthorDecision | None = None
    author_decision_by: str | None = None
    author_decision_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_timing_and_decision(self) -> 'AgentRun':
        if self.updated_at < self.created_at:
            raise ValueError('updated_at cannot precede created_at')
        if self.completed_at and not self.started_at:
            raise ValueError('completed_at requires started_at')
        if self.completed_at and self.completed_at < self.started_at:
            raise ValueError('completed_at cannot precede started_at')
        if self.author_decision and (
            not self.author_decision_by or self.author_decision_at is None
        ):
            raise ValueError('author decision requires decision maker and timestamp')
        if self.status is AgentRunStatus.IMPORTED and (
            self.author_decision is not AgentAuthorDecision.APPROVE_IMPORT
        ):
            raise ValueError('IMPORTED runs require APPROVE_IMPORT')
        return self
