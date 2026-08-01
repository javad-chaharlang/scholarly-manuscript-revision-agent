'''Persistent Phase 8 project-state and local registry records.'''

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProjectState(str, Enum):
    NEW = 'NEW'
    INTAKE_PENDING = 'INTAKE_PENDING'
    INTAKE_REVIEW = 'INTAKE_REVIEW'
    GAP_ANALYSIS_PENDING = 'GAP_ANALYSIS_PENDING'
    PLAN_APPROVAL = 'PLAN_APPROVAL'
    REVISION_DRAFTING = 'REVISION_DRAFTING'
    TEXT_APPROVAL = 'TEXT_APPROVAL'
    REVISION_APPLICATION = 'REVISION_APPLICATION'
    SCIENTIFIC_QA = 'SCIENTIFIC_QA'
    RESPONSE_PREPARATION = 'RESPONSE_PREPARATION'
    VISUAL_QA = 'VISUAL_QA'
    READY_FOR_RELEASE = 'READY_FOR_RELEASE'
    RELEASED = 'RELEASED'
    BLOCKED = 'BLOCKED'


class ProjectStateRecord(BaseModel):
    '''Current state only; the append-only timeline retains all prior events.'''

    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    schema_version: int = 1
    project_id: str = Field(min_length=1)
    state: ProjectState
    previous_state: ProjectState | None = None
    blocked_from: ProjectState | None = None
    blockers: list[str] = Field(default_factory=list)
    next_required_action: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    updated_at: datetime

    @field_validator('blockers')
    @classmethod
    def nonblank_blockers(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('blockers cannot contain blank values')
        return list(dict.fromkeys(values))

    @model_validator(mode='after')
    def blocked_state_has_context(self) -> 'ProjectStateRecord':
        if self.state is ProjectState.BLOCKED:
            if not self.blockers:
                raise ValueError('BLOCKED state requires at least one blocker')
            if self.blocked_from in {None, ProjectState.BLOCKED}:
                raise ValueError('BLOCKED state requires the prior workflow state')
        elif self.blockers:
            raise ValueError('active workflow states cannot retain blockers')
        return self


class ProjectAuditEvent(BaseModel):
    '''Confidentiality-safe event; detailed author text stays in governed records.'''

    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: int = 1
    sequence: int = Field(ge=0)
    timestamp: datetime
    project_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    from_state: ProjectState | None = None
    to_state: ProjectState
    action: str = Field(min_length=1)
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class ProjectRegistryEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    manuscript_id: str = Field(min_length=1)
    project_root: str = Field(min_length=1)
    state: ProjectState
    created_at: datetime
    updated_at: datetime
    archived: bool = False
    archived_at: datetime | None = None

    @field_validator('project_root')
    @classmethod
    def absolute_project_root(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError('registry project_root must be absolute')
        return str(path.resolve())


class ProjectRegistryFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1
    projects: list[ProjectRegistryEntry] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_projects(self) -> 'ProjectRegistryFile':
        ids = [item.project_id for item in self.projects]
        roots = [item.project_root.casefold() for item in self.projects]
        if len(ids) != len(set(ids)) or len(roots) != len(set(roots)):
            raise ValueError('registry project IDs and roots must be unique')
        return self
