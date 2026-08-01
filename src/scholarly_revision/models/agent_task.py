'''Persistent semantic-agent task records and approval gates.'''

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentTaskType(str, Enum):
    COMMENT_INTERPRETATION = 'COMMENT_INTERPRETATION'
    GAP_ANALYSIS = 'GAP_ANALYSIS'
    REVISION_PLAN_DRAFT = 'REVISION_PLAN_DRAFT'
    REVISION_TEXT_DRAFT = 'REVISION_TEXT_DRAFT'
    REFERENCE_NEED_ANALYSIS = 'REFERENCE_NEED_ANALYSIS'
    SEMANTIC_QA_REVIEW = 'SEMANTIC_QA_REVIEW'
    RESPONSE_LETTER_DRAFT = 'RESPONSE_LETTER_DRAFT'
    GENERAL_RESEARCH_NOTE = 'GENERAL_RESEARCH_NOTE'


class AgentTaskStatus(str, Enum):
    CREATED = 'CREATED'
    CONTEXT_READY = 'CONTEXT_READY'
    WAITING_FOR_TRANSMISSION_APPROVAL = 'WAITING_FOR_TRANSMISSION_APPROVAL'
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


class AgentTaskPriority(str, Enum):
    LOW = 'LOW'
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'


class TransmissionDecision(str, Enum):
    APPROVE_TRANSMISSION = 'APPROVE_TRANSMISSION'
    MODIFY_CONTEXT = 'MODIFY_CONTEXT'
    CANCEL_TASK = 'CANCEL_TASK'


class AgentTask(BaseModel):
    '''One immutable-scope semantic request; approval is always explicit.'''

    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    task_id: str = Field(pattern=r'^TASK-[A-Z0-9-]{8,}$')
    project_id: str = Field(min_length=1)
    task_type: AgentTaskType
    related_comment_ids: list[str] = Field(default_factory=list)
    related_action_ids: list[str] = Field(default_factory=list)
    source_element_ids: list[str] = Field(default_factory=list)
    requested_output_schema: str = Field(min_length=1)
    context_policy: str = Field(min_length=1)
    prompt_template: str = Field(min_length=1)
    status: AgentTaskStatus = AgentTaskStatus.CREATED
    priority: AgentTaskPriority = AgentTaskPriority.NORMAL
    approval_required: bool = True
    created_by: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    purpose: str = Field(min_length=1)
    transmission_decision: TransmissionDecision | None = None
    transmission_approved_by: str | None = None
    transmission_approved_at: datetime | None = None
    context_manifest_sha256: str | None = None
    retry_of_task_id: str | None = None
    retry_instruction: str | None = None
    cancel_requested: bool = False
    active_run_id: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None

    @field_validator(
        'related_comment_ids', 'related_action_ids', 'source_element_ids',
    )
    @classmethod
    def unique_nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('identifier lists cannot contain blank values')
        if len(values) != len(set(values)):
            raise ValueError('identifier lists cannot contain duplicates')
        return values

    @model_validator(mode='after')
    def enforce_transmission_gate(self) -> 'AgentTask':
        if self.updated_at < self.created_at:
            raise ValueError('updated_at cannot precede created_at')
        approved = self.transmission_decision is TransmissionDecision.APPROVE_TRANSMISSION
        if approved and (not self.transmission_approved_by or self.transmission_approved_at is None):
            raise ValueError('transmission approval requires approver and timestamp')
        if self.status in {
            AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING,
            AgentTaskStatus.COMPLETED_RAW, AgentTaskStatus.VALIDATING,
            AgentTaskStatus.VALIDATED, AgentTaskStatus.AUTHOR_REVIEW,
            AgentTaskStatus.APPROVED, AgentTaskStatus.IMPORTED,
        } and not approved:
            raise ValueError(f'{self.status.value} requires APPROVE_TRANSMISSION')
        if self.status is AgentTaskStatus.IMPORTED and not self.active_run_id:
            raise ValueError('IMPORTED tasks require a linked run')
        return self
