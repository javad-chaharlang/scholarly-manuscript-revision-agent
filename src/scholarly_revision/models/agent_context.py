'''Validated, reviewable context packages for semantic-agent transmission.'''

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContextPolicy(str, Enum):
    MINIMAL_COMMENT_CONTEXT = 'MINIMAL_COMMENT_CONTEXT'
    SECTION_CONTEXT = 'SECTION_CONTEXT'
    EXTENDED_SECTION_CONTEXT = 'EXTENDED_SECTION_CONTEXT'
    RESULTS_CONTEXT = 'RESULTS_CONTEXT'
    REFERENCE_CONTEXT = 'REFERENCE_CONTEXT'
    RESPONSE_CONTEXT = 'RESPONSE_CONTEXT'
    CUSTOM_AUTHOR_APPROVED_CONTEXT = 'CUSTOM_AUTHOR_APPROVED_CONTEXT'


class ContextReviewerComment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    comment_id: str
    exact_comment: str


class ContextManuscriptSection(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    section: str
    paragraph_ids: list[str] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)


class AgentContextManifest(BaseModel):
    '''The complete package shown to the author before transmission.'''

    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: int = 1
    context_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    context_policy: ContextPolicy
    prepared_at: datetime
    reviewer_comments_included: list[ContextReviewerComment] = Field(default_factory=list)
    manuscript_sections_included: list[ContextManuscriptSection] = Field(default_factory=list)
    paragraph_ids_included: list[str] = Field(default_factory=list)
    evidence_records_included: list[dict[str, object]] = Field(default_factory=list)
    result_records_included: list[dict[str, object]] = Field(default_factory=list)
    references_included: list[dict[str, object]] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)
    total_character_count: int = Field(ge=0)
    input_file_hashes: dict[str, str] = Field(default_factory=dict)
    transmitted_payload: dict[str, object]
    custom_context_author_approved: bool = False

    @field_validator('paragraph_ids_included', 'exclusions', 'redactions')
    @classmethod
    def unique_nonblank(cls, values: list[str]) -> list[str]:
        if any(not str(value).strip() for value in values):
            raise ValueError('context lists cannot contain blank values')
        return list(dict.fromkeys(values))

    @model_validator(mode='after')
    def validate_manifest(self) -> 'AgentContextManifest':
        if (
            self.context_policy is ContextPolicy.CUSTOM_AUTHOR_APPROVED_CONTEXT
            and not self.custom_context_author_approved
        ):
            raise ValueError('custom context requires explicit author approval')
        actual = len(json.dumps(
            self.transmitted_payload, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'),
        ))
        if self.total_character_count != actual:
            raise ValueError('total_character_count does not match transmitted payload')
        return self
