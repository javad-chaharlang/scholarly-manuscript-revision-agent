'''Reviewer-comment inventory and manuscript revision actions.'''

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import (
    ApprovalState,
    ChangeType,
    CommentCategory,
    CommentPriority,
    EvidenceStatus,
    HighlightColor,
    ReviewerSource,
    RevisionStatus,
)


COMMENT_ID_PATTERN = re.compile(
    r'^(?P<source>R(?P<reviewer>[1-9]\d*)|ED|GEN)-C(?P<sequence>\d{2,})$'
)


def _validated_comment_id(value: str) -> str:
    if not COMMENT_ID_PATTERN.fullmatch(value):
        raise ValueError(
            'comment ID must match R1-C01, R2-C03, ED-C01, or GEN-C01'
        )
    return value


def _highlight_for_comment_data(data: dict[str, Any]) -> HighlightColor | None:
    source = data.get('reviewer_source')
    if isinstance(source, ReviewerSource):
        source = source.value

    if data.get('shared_with'):
        return HighlightColor.VIOLET
    if source in {ReviewerSource.EDITOR.value, ReviewerSource.GENERAL.value}:
        return HighlightColor.VIOLET
    if source == ReviewerSource.REVIEWER.value:
        reviewer_number = data.get('reviewer_number')
        if reviewer_number == 1:
            return HighlightColor.YELLOW
        if reviewer_number == 2:
            return HighlightColor.BRIGHT_GREEN
    return None


def _highlight_for_action_ids(comment_ids: list[str]) -> HighlightColor | None:
    sources = {comment_id.split('-', 1)[0] for comment_id in comment_ids}
    if not sources:
        return None
    if sources == {'R1'}:
        return HighlightColor.YELLOW
    if sources == {'R2'}:
        return HighlightColor.BRIGHT_GREEN
    return HighlightColor.VIOLET


def _apply_or_check_highlight(
    data: dict[str, Any], expected: HighlightColor | None
) -> dict[str, Any]:
    if expected is None:
        raise ValueError('no repository highlight policy exists for this reviewer')
    supplied = data.get('highlight')
    if supplied is None:
        data['highlight'] = expected
        return data
    try:
        supplied_color = HighlightColor(supplied)
    except ValueError as exc:
        raise ValueError(f'unsupported highlight color: {supplied}') from exc
    if supplied_color is not expected:
        raise ValueError(
            f'highlight {supplied_color.value} conflicts with required '
            f'{expected.value}'
        )
    return data


class ReviewerComment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    comment_id: str
    reviewer_source: ReviewerSource
    reviewer_number: int | None = Field(default=None, ge=1)
    sequence_number: int = Field(ge=1)
    original_comment: str
    normalized_comment: str | None = None
    categories: list[CommentCategory] = Field(default_factory=list)
    priority: CommentPriority = CommentPriority.MAJOR
    interpretation: str | None = None
    required_actions: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    shared_with: list[str] = Field(default_factory=list)
    status: RevisionStatus = RevisionStatus.NOT_STARTED
    highlight: HighlightColor | None = None
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_REQUIRED
    author_decision: str | None = None
    notes: str | None = None

    @model_validator(mode='before')
    @classmethod
    def assign_policy_highlight(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        return _apply_or_check_highlight(data, _highlight_for_comment_data(data))

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('original_comment')
    @classmethod
    def reject_empty_original_comment(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('reviewer comments must not be empty')
        return value

    @field_validator('normalized_comment')
    @classmethod
    def reject_empty_normalized_comment(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError('normalized_comment must be non-empty when provided')
        return value

    @model_validator(mode='after')
    def validate_identity_and_state(self) -> ReviewerComment:
        match = COMMENT_ID_PATTERN.fullmatch(self.comment_id)
        assert match is not None
        id_source = match.group('source')
        id_reviewer = match.group('reviewer')
        id_sequence = int(match.group('sequence'))

        if id_sequence != self.sequence_number:
            raise ValueError('sequence_number must match the comment ID')

        if self.reviewer_source is ReviewerSource.REVIEWER:
            if self.reviewer_number is None:
                raise ValueError('reviewer_number is required for reviewer comments')
            if id_reviewer is None or int(id_reviewer) != self.reviewer_number:
                raise ValueError('reviewer_number and source must match the comment ID')
        elif self.reviewer_source is ReviewerSource.GENERAL:
            if self.reviewer_number is not None:
                raise ValueError('reviewer_number must be absent for GENERAL comments')
            if id_source != 'GEN':
                raise ValueError('GENERAL comments must use a GEN comment ID')
        else:
            if self.reviewer_number is not None:
                raise ValueError('reviewer_number must be absent for EDITOR comments')
            if id_source != 'ED':
                raise ValueError('EDITOR comments must use an ED comment ID')

        if (
            self.normalized_comment is not None
            and self.normalized_comment == self.original_comment
        ):
            raise ValueError(
                'normalized_comment must remain distinct from original_comment; '
                'omit it when no normalization was needed'
            )

        if self.status is RevisionStatus.VERIFIED and self.evidence_status not in {
            EvidenceStatus.NOT_REQUIRED,
            EvidenceStatus.VERIFIED,
        }:
            raise ValueError('VERIFIED comments cannot rely on unverified evidence')
        return self


class RevisionAction(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    action_id: str = Field(min_length=1)
    comment_ids: list[str] = Field(min_length=1)
    change_type: ChangeType
    target_section: str = Field(min_length=1)
    target_object: str | None = None
    old_text_summary: str | None = None
    proposed_text: str | None = None
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    status: RevisionStatus = RevisionStatus.PLANNED
    approval_state: ApprovalState = ApprovalState.PENDING
    highlight: HighlightColor | None = None
    applied_location: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None

    @model_validator(mode='before')
    @classmethod
    def assign_policy_highlight(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_ids = data.get('comment_ids') or []
        if isinstance(raw_ids, (str, bytes)):
            return data
        return _apply_or_check_highlight(
            data, _highlight_for_action_ids(list(raw_ids))
        )

    @field_validator('comment_ids')
    @classmethod
    def validate_comment_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        if len(values) != len(set(values)):
            raise ValueError('comment_ids must not contain duplicates')
        return values

    @model_validator(mode='after')
    def validate_applied_and_verified_states(self) -> RevisionAction:
        if self.status in {RevisionStatus.APPLIED, RevisionStatus.VERIFIED}:
            if not self.applied_location or not self.applied_location.strip():
                raise ValueError(
                    f'{self.status.value} actions require applied_location'
                )
        if self.status is RevisionStatus.VERIFIED:
            if not self.verified_by or not self.verified_by.strip():
                raise ValueError('VERIFIED actions require verified_by')
            if self.verified_at is None:
                raise ValueError('VERIFIED actions require verified_at')
        return self
