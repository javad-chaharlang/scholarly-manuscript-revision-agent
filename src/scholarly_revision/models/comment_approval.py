'''Researcher approval of one reviewer response and all linked manuscript drafts.'''

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.reviewer import _validated_comment_id


_SHA256 = re.compile(r'^[0-9a-f]{64}$')


class CommentApprovalDecision(str, Enum):
    APPROVE_PACKAGE = 'APPROVE_PACKAGE'
    APPROVE_WITH_MODIFICATION = 'APPROVE_WITH_MODIFICATION'
    REQUEST_REWRITE = 'REQUEST_REWRITE'
    NEED_MORE_EVIDENCE = 'NEED_MORE_EVIDENCE'
    DEFER = 'DEFER'
    REJECT_REQUEST = 'REJECT_REQUEST'


class ProposedCommentResponse(BaseModel):
    '''Schema-constrained pre-application response proposed by the semantic agent.'''

    model_config = ConfigDict(extra='forbid', frozen=True)

    comment_id: str
    exact_comment: str = Field(min_length=1)
    proposed_response: str = Field(min_length=1)
    related_draft_ids: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('related_draft_ids', 'uncertainties')
    @classmethod
    def validate_lists(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('identifier and uncertainty lists cannot contain blanks')
        if len(values) != len(set(values)):
            raise ValueError('identifier and uncertainty lists cannot contain duplicates')
        return values


class CommentApprovalRecord(BaseModel):
    '''One atomic pre-application decision for a reviewer comment.'''

    model_config = ConfigDict(extra='forbid', frozen=True)

    approval_id: str = Field(min_length=1)
    comment_id: str
    exact_comment_sha256: str
    source_document_hash: str
    related_draft_ids: list[str] = Field(default_factory=list)
    related_draft_hashes: dict[str, str] = Field(default_factory=dict)
    proposed_response: str = Field(min_length=1)
    approved_response: str | None = None
    author_modified_response: str | None = None
    approved_draft_ids: list[str] = Field(default_factory=list)
    decision: CommentApprovalDecision
    decision_maker: str = Field(min_length=1)
    decision_timestamp: datetime
    author_note: str | None = None
    evidence_request: str | None = None
    rewrite_instruction: str | None = None

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('exact_comment_sha256', 'source_document_hash')
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256.fullmatch(normalized):
            raise ValueError('hash values must be lowercase SHA-256 hex strings')
        return normalized

    @field_validator('related_draft_hashes')
    @classmethod
    def validate_draft_hashes(cls, values: dict[str, str]) -> dict[str, str]:
        normalized = {key: value.lower() for key, value in values.items()}
        if any(not key.strip() for key in normalized):
            raise ValueError('draft hash keys cannot be blank')
        if any(not _SHA256.fullmatch(value) for value in normalized.values()):
            raise ValueError('draft fingerprints must be lowercase SHA-256 hex strings')
        return normalized

    @field_validator('related_draft_ids', 'approved_draft_ids')
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError('draft IDs cannot be blank')
        if len(values) != len(set(values)):
            raise ValueError('draft IDs cannot contain duplicates')
        return values

    @model_validator(mode='after')
    def validate_decision(self) -> 'CommentApprovalRecord':
        related = set(self.related_draft_ids)
        approved = set(self.approved_draft_ids)
        if set(self.related_draft_hashes) != related:
            raise ValueError('related_draft_hashes must cover every related draft exactly')
        if not approved.issubset(related):
            raise ValueError('approved_draft_ids must be a subset of related_draft_ids')
        if self.decision is CommentApprovalDecision.APPROVE_PACKAGE:
            if self.approved_response != self.proposed_response:
                raise ValueError('APPROVE_PACKAGE must preserve proposed_response exactly')
        elif self.decision is CommentApprovalDecision.APPROVE_WITH_MODIFICATION:
            if not (self.author_modified_response or '').strip():
                raise ValueError('modified approval requires author_modified_response')
            if self.approved_response != self.author_modified_response:
                raise ValueError('approved_response must preserve the author modification')
        else:
            if self.approved_response is not None or self.approved_draft_ids:
                raise ValueError('non-approval decisions cannot approve response or drafts')
            if self.decision is CommentApprovalDecision.REQUEST_REWRITE and not (
                self.rewrite_instruction or ''
            ).strip():
                raise ValueError('REQUEST_REWRITE requires rewrite_instruction')
            if self.decision is CommentApprovalDecision.NEED_MORE_EVIDENCE and not (
                self.evidence_request or ''
            ).strip():
                raise ValueError('NEED_MORE_EVIDENCE requires evidence_request')
            if self.decision in {
                CommentApprovalDecision.DEFER,
                CommentApprovalDecision.REJECT_REQUEST,
            } and not (self.author_note or '').strip():
                raise ValueError(f'{self.decision.value} requires an author note')
        return self


class CommentApprovalBundle(BaseModel):
    '''Complete per-comment gate evaluated before any manuscript mutation.'''

    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: int = 1
    source_document_hash: str
    records: list[CommentApprovalRecord] = Field(min_length=1)

    @field_validator('source_document_hash')
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        normalized = value.lower()
        if not _SHA256.fullmatch(normalized):
            raise ValueError('source_document_hash must be lowercase SHA-256 hex')
        return normalized

    @model_validator(mode='after')
    def validate_bundle(self) -> 'CommentApprovalBundle':
        comment_ids = [record.comment_id for record in self.records]
        if len(comment_ids) != len(set(comment_ids)):
            raise ValueError('one approval record is allowed per reviewer comment')
        if any(
            record.source_document_hash != self.source_document_hash
            for record in self.records
        ):
            raise ValueError('all records must target the bundle source document')
        return self

    @property
    def approved_comment_ids(self) -> set[str]:
        allowed = {
            CommentApprovalDecision.APPROVE_PACKAGE,
            CommentApprovalDecision.APPROVE_WITH_MODIFICATION,
        }
        return {
            record.comment_id for record in self.records
            if record.decision in allowed
        }

    @property
    def approved_draft_ids(self) -> set[str]:
        return {
            draft_id
            for record in self.records
            for draft_id in record.approved_draft_ids
        }
