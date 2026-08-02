'''Validated Phase 7 response-to-reviewers records.'''

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import EvidenceStatus, HighlightColor, ReviewerSource
from scholarly_revision.models.reviewer import (
    _validated_comment_id,
    highlight_for_reviewer_number,
)


class ResponseStringEnum(str, Enum):
    '''String enum with stable JSON serialization.'''


class ResponseStatus(ResponseStringEnum):
    NOT_STARTED = 'NOT_STARTED'
    DRAFTED = 'DRAFTED'
    AUTHOR_REVIEW = 'AUTHOR_REVIEW'
    APPROVED = 'APPROVED'
    VERIFIED = 'VERIFIED'
    BLOCKED = 'BLOCKED'


class LocationStatus(ResponseStringEnum):
    NOT_REQUIRED = 'NOT_REQUIRED'
    UNVERIFIED = 'UNVERIFIED'
    SECTION_VERIFIED = 'SECTION_VERIFIED'
    OBJECT_VERIFIED = 'OBJECT_VERIFIED'
    PAGE_VERIFIED = 'PAGE_VERIFIED'
    PAGE_AND_LINES_VERIFIED = 'PAGE_AND_LINES_VERIFIED'


class CommentResolution(ResponseStringEnum):
    FULLY_ADDRESSED = 'FULLY_ADDRESSED'
    PARTIALLY_ADDRESSED = 'PARTIALLY_ADDRESSED'
    RESPECTFULLY_DECLINED = 'RESPECTFULLY_DECLINED'
    DEFERRED = 'DEFERRED'
    BLOCKED_BY_MISSING_EVIDENCE = 'BLOCKED_BY_MISSING_EVIDENCE'
    NOT_APPLICABLE = 'NOT_APPLICABLE'


def _unique_nonblank(values: list[str]) -> list[str]:
    if any(not str(value).strip() for value in values):
        raise ValueError('identifier and location lists cannot contain blank values')
    if len(values) != len(set(values)):
        raise ValueError('identifier and location lists cannot contain duplicates')
    return values


class ResponseEntry(BaseModel):
    '''One response record linked to the source-of-truth reviewer comment.'''

    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    response_entry_id: str = Field(min_length=1)
    reviewer_source: ReviewerSource
    reviewer_number: int | None = Field(default=None, ge=1)
    comment_id: str
    sequence_number: int = Field(ge=1)
    exact_comment: str
    author_response: str = ''
    changes_made: str = ''
    verified_locations: list[str] = Field(default_factory=list)
    related_action_ids: list[str] = Field(default_factory=list)
    related_change_ids: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    related_reference_ids: list[str] = Field(default_factory=list)
    highlight: HighlightColor
    response_status: ResponseStatus = ResponseStatus.NOT_STARTED
    location_status: LocationStatus = LocationStatus.UNVERIFIED
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_REQUIRED
    author_approved: bool = False
    verification_notes: list[str] = Field(default_factory=list)
    resolution: CommentResolution | None = None
    approved_interpretation: str | None = None
    unresolved_limitations: list[str] = Field(default_factory=list)
    author_justification: str | None = None

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('exact_comment')
    @classmethod
    def preserve_nonempty_comment(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('exact_comment must preserve non-empty reviewer text')
        return value

    @field_validator(
        'verified_locations', 'related_action_ids', 'related_change_ids',
        'related_evidence_ids', 'related_reference_ids', 'verification_notes',
        'unresolved_limitations',
    )
    @classmethod
    def validate_lists(cls, values: list[str]) -> list[str]:
        return _unique_nonblank(values)

    @model_validator(mode='after')
    def validate_identity_policy_and_state(self) -> 'ResponseEntry':
        prefix, raw_sequence = self.comment_id.split('-C', 1)
        if int(raw_sequence) != self.sequence_number:
            raise ValueError('sequence_number must match comment_id')
        if self.reviewer_source is ReviewerSource.REVIEWER:
            if self.reviewer_number is None or prefix != f'R{self.reviewer_number}':
                raise ValueError('reviewer identity must match comment_id')
            expected = highlight_for_reviewer_number(self.reviewer_number)
        else:
            if self.reviewer_number is not None:
                raise ValueError('editor/general entries cannot have reviewer_number')
            expected = HighlightColor.VIOLET
        if self.highlight is not expected:
            raise ValueError(f'highlight must be {expected.value} for {self.comment_id}')
        if self.location_status is LocationStatus.NOT_REQUIRED and self.verified_locations:
            raise ValueError('NOT_REQUIRED location status cannot contain verified locations')
        if self.location_status not in {LocationStatus.NOT_REQUIRED, LocationStatus.UNVERIFIED}:
            if not self.verified_locations:
                raise ValueError('a verified location status requires verified_locations')
        if self.related_evidence_ids and self.evidence_status is not EvidenceStatus.VERIFIED:
            raise ValueError('cited evidence must have VERIFIED evidence status')
        if self.changes_made.strip() and not self.related_change_ids:
            raise ValueError('changes_made requires related ChangeLog IDs')
        if self.resolution is CommentResolution.RESPECTFULLY_DECLINED:
            if not self.author_approved:
                raise ValueError('declining a reviewer request requires author approval')
            if not (self.author_justification or '').strip():
                raise ValueError('declining a reviewer request requires justification')
        if self.resolution is CommentResolution.PARTIALLY_ADDRESSED and not self.author_approved:
            raise ValueError('a partially addressed request requires author approval')
        if self.resolution in {
            CommentResolution.DEFERRED,
            CommentResolution.BLOCKED_BY_MISSING_EVIDENCE,
        } and not self.unresolved_limitations:
            raise ValueError('deferred or blocked responses must state unresolved limitations')
        if self.response_status is ResponseStatus.VERIFIED:
            missing: list[str] = []
            if not self.author_response.strip():
                missing.append('author_response')
            if not self.author_approved:
                missing.append('author approval')
            if self.resolution is None:
                missing.append('explicit resolution')
            if self.changes_made.strip() and self.location_status in {
                LocationStatus.NOT_REQUIRED, LocationStatus.UNVERIFIED,
            }:
                missing.append('verified location')
            if missing:
                raise ValueError('VERIFIED response is missing: ' + ', '.join(missing))
        return self


class ReviewerResponseSection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    reviewer_source: ReviewerSource
    reviewer_number: int | None = Field(default=None, ge=1)
    entries: list[ResponseEntry] = Field(default_factory=list)


class EditorCoverLetter(BaseModel):
    model_config = ConfigDict(extra='forbid')
    salutation: str = 'Dear Editor,'
    body_paragraphs: list[str] = Field(default_factory=list)
    closing: str = 'Sincerely,'
    verified_metadata_only: bool = True
    verification_notes: list[str] = Field(default_factory=list)


class ResponsePackage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1
    generated_at: datetime
    manuscript_title: str = Field(min_length=1)
    manuscript_id: str = Field(min_length=1)
    journal: str = Field(min_length=1)
    revision_round: int = Field(ge=1)
    cover_letter: EditorCoverLetter
    summary_of_major_revisions: list[str] = Field(default_factory=list)
    sections: list[ReviewerResponseSection] = Field(default_factory=list)
    general_revisions: list[str] = Field(default_factory=list)
    closing_statement: str = Field(min_length=1)
    package_status: ResponseStatus = ResponseStatus.DRAFTED
    source_hashes: dict[str, str] = Field(default_factory=dict)
    verification_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def entries(self) -> list[ResponseEntry]:
        return [entry for section in self.sections for entry in section.entries]

    @model_validator(mode='after')
    def unique_entries(self) -> 'ResponsePackage':
        ids = [entry.response_entry_id for entry in self.entries]
        comments = [entry.comment_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate response_entry_id values are not permitted')
        if len(comments) != len(set(comments)):
            raise ValueError('duplicate response entries for one comment are not permitted')
        if self.package_status is ResponseStatus.VERIFIED and any(
            entry.response_status is not ResponseStatus.VERIFIED for entry in self.entries
        ):
            raise ValueError('a VERIFIED package requires every entry to be VERIFIED')
        return self
