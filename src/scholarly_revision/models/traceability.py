'''Cross-record traceability and response-letter entries.'''

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import HighlightColor, RevisionStatus
from scholarly_revision.models.reviewer import (
    ReviewerComment,
    RevisionAction,
    _validated_comment_id,
)


class TraceabilityRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    trace_id: str = Field(min_length=1)
    comment_id: str
    interpretation_complete: bool = False
    required_action_ids: list[str] = Field(default_factory=list)
    manuscript_change_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    response_entry_id: str | None = None
    location_verified: bool = False
    highlight_verified: bool = False
    scientific_claims_verified: bool = False
    final_status: RevisionStatus = RevisionStatus.NOT_STARTED
    unresolved_issues: list[str] = Field(default_factory=list)
    author_approved: bool = False
    last_checked_at: datetime | None = None

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @model_validator(mode='after')
    def validate_final_traceability(self) -> TraceabilityRecord:
        if self.final_status is not RevisionStatus.VERIFIED:
            return self

        missing: list[str] = []
        if not self.interpretation_complete:
            missing.append('interpretation')
        if not self.required_action_ids:
            missing.append('required_action_ids')
        if not self.manuscript_change_ids:
            missing.append('manuscript_change_ids')
        if not self.response_entry_id:
            missing.append('response_entry_id')
        if not self.location_verified:
            missing.append('location verification')
        if not self.highlight_verified:
            missing.append('highlight verification')
        if not self.scientific_claims_verified:
            missing.append('scientific-claims verification')
        if not self.author_approved:
            missing.append('author approval')
        if self.last_checked_at is None:
            missing.append('last_checked_at')
        if self.unresolved_issues:
            missing.append('unresolved issues')
        if missing:
            raise ValueError(
                'final traceability status cannot be VERIFIED; missing: '
                + ', '.join(missing)
            )
        return self


class ResponseLetterEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    response_entry_id: str = Field(min_length=1)
    comment_id: str
    exact_comment: str
    author_response: str = Field(min_length=1)
    changes_made: str = ''
    location: str | None = None
    highlight: HighlightColor
    verification_status: RevisionStatus = RevisionStatus.DRAFTED

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('exact_comment')
    @classmethod
    def reject_empty_exact_comment(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('exact_comment must preserve non-empty reviewer text')
        return value

    @model_validator(mode='after')
    def validate_verified_location(self) -> ResponseLetterEntry:
        if (
            self.verification_status is RevisionStatus.VERIFIED
            and self.changes_made.strip()
            and (not self.location or not self.location.strip())
        ):
            raise ValueError(
                'VERIFIED response entries reporting changes require a location'
            )
        return self

    def validate_against_source(
        self,
        comment: ReviewerComment,
        revision_actions: Iterable[RevisionAction],
    ) -> None:
        '''Validate exact text and every reported change against verified actions.'''

        if self.comment_id != comment.comment_id:
            raise ValueError('response entry and reviewer comment IDs do not match')
        if self.exact_comment != comment.original_comment:
            raise ValueError('exact_comment does not preserve the reviewer comment')
        if not self.changes_made.strip():
            return
        matching_verified_actions = [
            action
            for action in revision_actions
            if self.comment_id in action.comment_ids
            and action.status is RevisionStatus.VERIFIED
        ]
        if not matching_verified_actions:
            raise ValueError(
                'reported manuscript changes require a corresponding '
                'verified RevisionAction'
            )
