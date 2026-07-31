'''Exact-text drafting, approval, application, and audit records for Phase 5.'''

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import (
    HighlightColor,
    RevisionDraftStatus,
    RevisionOperation,
    RevisionTextApprovalState,
    RevisionTextDecision,
)
from scholarly_revision.models.reviewer import _validated_comment_id


_SHA256 = re.compile(r'^[0-9a-f]{64}$')


class RevisionDraft(BaseModel):
    '''One executable exact-text proposal linked to one approved action.'''

    model_config = ConfigDict(extra='forbid', frozen=True)

    draft_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    comment_ids: list[str] = Field(min_length=1)
    source_document_hash: str
    target_element_ids: list[str] = Field(min_length=1)
    target_section: str = Field(min_length=1)
    operation: RevisionOperation
    original_text_snapshot: str
    original_text_hash: str
    proposed_text: str = ''
    drafting_rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    scientific_claim_ids: list[str] = Field(default_factory=list)
    highlight: HighlightColor
    draft_status: RevisionDraftStatus = RevisionDraftStatus.PREPARED
    approval_state: RevisionTextApprovalState = RevisionTextApprovalState.PENDING
    author_decision: RevisionTextDecision | None = None
    author_modified_text: str | None = None
    author_note: str | None = None
    created_at: datetime
    updated_at: datetime

    deletion_justification: str | None = None
    table_id: str | None = None
    table_row: int | None = Field(default=None, ge=0)
    table_column: int | None = Field(default=None, ge=0)
    approved_text: str | None = None
    decision_maker: str | None = None
    decision_timestamp: datetime | None = None
    evidence_request: str | None = None
    rewrite_instruction: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    verified_locations: list[str] = Field(default_factory=list)
    compatible_with_draft_ids: list[str] = Field(default_factory=list)
    manual_handling_required: bool = False
    manual_handling_reasons: list[str] = Field(default_factory=list)
    application_status: str = 'NOT_APPLIED'
    output_version: str | None = None
    verified_location: str | None = None

    @field_validator('comment_ids')
    @classmethod
    def validate_comment_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        if len(values) != len(set(values)):
            raise ValueError('comment_ids must not contain duplicates')
        return values

    @field_validator(
        'target_element_ids', 'evidence_ids', 'reference_ids',
        'scientific_claim_ids', 'compatible_with_draft_ids',
    )
    @classmethod
    def validate_identifier_lists(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('identifier lists must not contain blank values')
        if len(values) != len(set(values)):
            raise ValueError('identifier lists must not contain duplicates')
        return values

    @field_validator('source_document_hash', 'original_text_hash')
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256.fullmatch(normalized):
            raise ValueError('hash values must be lowercase SHA-256 hex strings')
        return normalized

    @model_validator(mode='after')
    def validate_draft_state(self) -> 'RevisionDraft':
        if self.updated_at < self.created_at:
            raise ValueError('updated_at cannot precede created_at')
        if self.operation is RevisionOperation.DELETE_PARAGRAPH:
            if not self.deletion_justification or not self.deletion_justification.strip():
                raise ValueError('DELETE_PARAGRAPH requires deletion justification')
        elif not self.proposed_text.strip() and self.draft_status is not RevisionDraftStatus.PREPARED:
            raise ValueError(
                'empty proposed text is permitted only for a prepared template or deletion'
            )

        if self.operation is RevisionOperation.REPLACE_TABLE_CELL:
            if not self.table_id or self.table_row is None or self.table_column is None:
                raise ValueError('table-cell changes require table ID, row, and column')

        if self.author_decision is RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION:
            if not self.author_modified_text or not self.author_modified_text.strip():
                raise ValueError('modified text approval requires author_modified_text')
            if self.approved_text != self.author_modified_text:
                raise ValueError('approved_text must preserve author_modified_text exactly')
        if self.author_decision is RevisionTextDecision.APPROVE_TEXT:
            if self.approved_text != self.proposed_text:
                raise ValueError('APPROVE_TEXT must approve proposed_text exactly')

        if self.draft_status is RevisionDraftStatus.APPLIED:
            if self.approval_state is not RevisionTextApprovalState.APPROVED:
                raise ValueError('a draft cannot be APPLIED before exact-text approval')
            if self.author_decision not in {
                RevisionTextDecision.APPROVE_TEXT,
                RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION,
            }:
                raise ValueError('APPLIED drafts require an explicit approval decision')
            if self.manual_handling_required:
                raise ValueError('manual-handling drafts cannot be APPLIED')

        if self.scientific_claim_ids and not self.evidence_ids:
            if self.author_decision not in {
                RevisionTextDecision.APPROVE_TEXT,
                RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION,
            }:
                raise ValueError(
                    'scientific claims require linked evidence or explicit author approval'
                )
        if self.manual_handling_required and not self.manual_handling_reasons:
            raise ValueError('manual_handling_required needs at least one reason')
        return self

    @property
    def text_for_application(self) -> str:
        if self.author_decision is RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION:
            return self.author_modified_text or ''
        return self.approved_text if self.approved_text is not None else self.proposed_text


class RevisionTextDecisionRecord(BaseModel):
    '''One explicit second-gate decision; blank input is never approval.'''

    model_config = ConfigDict(extra='forbid', frozen=True)

    draft_id: str = Field(min_length=1)
    decision: RevisionTextDecision
    decision_maker: str = Field(min_length=1)
    decision_timestamp: datetime
    approved_text: str | None = None
    author_modified_text: str | None = None
    author_note: str | None = None
    evidence_request: str | None = None
    rewrite_instruction: str | None = None
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_decision(self) -> 'RevisionTextDecisionRecord':
        if self.decision is RevisionTextDecision.APPROVE_TEXT:
            if self.approved_text is None:
                raise ValueError('APPROVE_TEXT requires approved_text')
        elif self.decision is RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION:
            if not self.author_modified_text or not self.author_modified_text.strip():
                raise ValueError('modified approval requires author_modified_text')
            if self.approved_text != self.author_modified_text:
                raise ValueError('approved_text must equal author_modified_text exactly')
        elif self.decision is RevisionTextDecision.REJECT_TEXT:
            if not self.author_note or not self.author_note.strip():
                raise ValueError('rejection requires a justification')
        elif self.decision is RevisionTextDecision.REQUEST_REWRITE:
            if not self.rewrite_instruction or not self.rewrite_instruction.strip():
                raise ValueError('rewrite request requires rewrite_instruction')
        elif self.decision is RevisionTextDecision.NEED_MORE_EVIDENCE:
            if not self.evidence_request or not self.evidence_request.strip():
                raise ValueError('need-more-evidence requires evidence_request')
        return self


class ChangeRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    change_id: str
    draft_id: str
    action_id: str
    comment_ids: list[str]
    operation: RevisionOperation
    target_section: str
    target_element_id: str
    old_text_hash: str
    new_text_hash: str
    old_text_summary: str
    new_text_summary: str
    highlight: HighlightColor
    application_timestamp: datetime
    output_document_version: str
    verification_status: str
    warnings: list[str] = Field(default_factory=list)


class DocumentVersionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    version: str
    role: str
    file_name: str
    source_hash: str
    output_hash: str
    parent_version: str | None = None
    creation_timestamp: datetime
    applied_change_ids: list[str] = Field(default_factory=list)
    verification_result: str
