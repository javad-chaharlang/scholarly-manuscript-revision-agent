'''Validated Phase 4 gap-analysis and approval records.'''

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import (
    ApprovalDecision,
    ChangeType,
    CoverageStatus,
    EvidenceStatus,
)
from scholarly_revision.models.reviewer import _validated_comment_id


class ManuscriptEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')

    evidence_id: str = Field(min_length=1)
    element_ids: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    status: EvidenceStatus = EvidenceStatus.PROVIDED
    location: str | None = None
    location_verified: bool = False


class ActionProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')

    proposal_id: str | None = None
    shared_action_key: str | None = None
    linked_comment_ids: list[str] = Field(default_factory=list)
    change_type: ChangeType = ChangeType.GENERAL_CORRECTION
    target_section: str = Field(min_length=1)
    target_object: str | None = None
    proposed_revision_summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_requirements: list[str] = Field(default_factory=list)
    reference_requirements: list[str] = Field(default_factory=list)
    experiment_requirements: list[str] = Field(default_factory=list)
    statistical_requirements: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)

    @field_validator('linked_comment_ids')
    @classmethod
    def validate_linked_comments(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        if len(values) != len(set(values)):
            raise ValueError('linked_comment_ids must not contain duplicates')
        return values


class GapAnalysisAssessment(BaseModel):
    '''Semantic fields remain nullable or empty until supplied by a human/Codex.'''

    model_config = ConfigDict(extra='forbid')

    comment_id: str
    original_comment: str
    coverage_status: CoverageStatus | None = None
    interpretation: str | None = None
    manuscript_evidence: list[ManuscriptEvidence] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    target_objects: list[str] = Field(default_factory=list)
    required_references: list[str] = Field(default_factory=list)
    required_experiments: list[str] = Field(default_factory=list)
    required_statistics: list[str] = Field(default_factory=list)
    author_decision_required: bool | None = None
    shared_with_comments: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    manual_review_required: bool | None = None
    verification_status: EvidenceStatus | None = None
    experiment_completion_claimed: bool = False
    experiment_evidence_ids: list[str] = Field(default_factory=list)
    verified_locations: list[str] = Field(default_factory=list)
    action_proposals: list[ActionProposal] = Field(default_factory=list)

    @field_validator('comment_id')
    @classmethod
    def validate_comment_id(cls, value: str) -> str:
        return _validated_comment_id(value)

    @field_validator('shared_with_comments')
    @classmethod
    def validate_shared_comments(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        return values


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    decision: ApprovalDecision
    author_note: str | None = None
    modified_action_text: str | None = None
    evidence_request: str | None = None
    decision_timestamp: datetime
    decision_maker: str = Field(min_length=1)
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_decision_requirements(self) -> 'ApprovalRecord':
        if self.decision is ApprovalDecision.REJECT_WITH_JUSTIFICATION:
            if not self.author_note or not self.author_note.strip():
                raise ValueError('rejection requires justification in author_note')
        if self.decision is ApprovalDecision.APPROVE_WITH_MODIFICATION:
            if not self.modified_action_text or not self.modified_action_text.strip():
                raise ValueError('approval with modification requires revised action text')
        if self.decision is ApprovalDecision.NEED_MORE_EVIDENCE:
            if not self.evidence_request or not self.evidence_request.strip():
                raise ValueError('need more evidence requires an evidence request')
        return self
