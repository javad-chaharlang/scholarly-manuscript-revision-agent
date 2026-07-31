'''Validated Phase 7 consistency, release-gate, and manifest records.'''

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.scientific_audit import (
    AuditIssueStatus, AuditSeverity, FinalReleaseReadiness,
)

MANUAL_VISUAL_QA_ARTIFACTS = (
    'Response_to_Reviewers.docx',
    'Revised_Manuscript_Highlighted.docx',
    'Revised_Manuscript_Clean.docx',
    'Revision_Master.xlsx',
    'Scientific_QA_Report.xlsx',
)


class ManualVisualQADecision(str, Enum):
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class ManualVisualQAArtifactDecision(BaseModel):
    '''Explicit human inspection decision for one final deliverable.'''

    model_config = ConfigDict(extra='forbid')
    artifact_name: str = Field(min_length=1)
    artifact_sha256: str
    opened_successfully: bool
    repair_warning_present: bool
    layout_acceptable: bool
    highlights_verified: bool
    tables_and_captions_acceptable: bool
    clean_highlight_text_equivalence_confirmed: bool
    reviewer_notes: str
    decision_maker: str = Field(min_length=1)
    decision_timestamp: datetime
    decision: ManualVisualQADecision

    @field_validator('artifact_name')
    @classmethod
    def supported_artifact(cls, value: str) -> str:
        if value not in MANUAL_VISUAL_QA_ARTIFACTS:
            raise ValueError('unsupported manual visual-QA artifact')
        return value

    @field_validator('artifact_sha256')
    @classmethod
    def valid_artifact_sha256(cls, value: str) -> str:
        value = value.lower()
        if not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('artifact_sha256 must be lowercase SHA-256 hex')
        return value

    @field_validator('decision_maker')
    @classmethod
    def nonblank_decision_maker(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('decision_maker cannot be blank')
        return value

    @field_validator('decision_timestamp')
    @classmethod
    def timezone_aware_decision(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('decision_timestamp must include a timezone')
        return value

    @model_validator(mode='after')
    def approved_decision_requires_passing_inspection(
        self,
    ) -> 'ManualVisualQAArtifactDecision':
        if self.decision is not ManualVisualQADecision.APPROVED:
            return self
        failures = []
        if not self.opened_successfully:
            failures.append('opened_successfully')
        if self.repair_warning_present:
            failures.append('repair_warning_present')
        for field in (
            'layout_acceptable',
            'highlights_verified',
            'tables_and_captions_acceptable',
            'clean_highlight_text_equivalence_confirmed',
        ):
            if not getattr(self, field):
                failures.append(field)
        if failures:
            raise ValueError(
                'APPROVED visual-QA decision has failed checks: '
                + ', '.join(failures)
            )
        return self


class ManualVisualQARecord(BaseModel):
    '''Complete human decision record for the five release artifacts.'''

    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1
    decisions: list[ManualVisualQAArtifactDecision]

    @model_validator(mode='after')
    def complete_artifact_scope(self) -> 'ManualVisualQARecord':
        names = [item.artifact_name for item in self.decisions]
        if len(names) != len(set(names)):
            raise ValueError('manual visual-QA artifacts cannot be duplicated')
        missing = sorted(set(MANUAL_VISUAL_QA_ARTIFACTS) - set(names))
        extra = sorted(set(names) - set(MANUAL_VISUAL_QA_ARTIFACTS))
        if missing or extra:
            raise ValueError(
                'manual visual-QA record must cover exactly the required artifacts; '
                f'missing={missing}, extra={extra}'
            )
        return self

    @property
    def all_approved(self) -> bool:
        return all(
            item.decision is ManualVisualQADecision.APPROVED
            for item in self.decisions
        )


class ConsistencyCategory(str, Enum):
    COMMENT_COVERAGE = 'COMMENT_COVERAGE'
    TRACEABILITY = 'TRACEABILITY'
    CHANGE_CLAIM = 'CHANGE_CLAIM'
    HIGHLIGHT = 'HIGHLIGHT'
    LOCATION = 'LOCATION'
    EVIDENCE = 'EVIDENCE'
    REFERENCE = 'REFERENCE'
    NUMERICAL = 'NUMERICAL'
    QA = 'QA'
    STATUS = 'STATUS'
    MANUSCRIPT_EQUIVALENCE = 'MANUSCRIPT_EQUIVALENCE'
    APPROVAL = 'APPROVAL'
    CONFIDENTIALITY = 'CONFIDENTIALITY'
    ARTIFACT = 'ARTIFACT'


class ConsistencyFinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    finding_id: str = Field(min_length=1)
    category: ConsistencyCategory
    severity: AuditSeverity
    description: str = Field(min_length=1)
    related_comment_ids: list[str] = Field(default_factory=list)
    related_action_ids: list[str] = Field(default_factory=list)
    related_change_ids: list[str] = Field(default_factory=list)
    related_response_entry_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    status: AuditIssueStatus = AuditIssueStatus.OPEN
    resolution: str | None = None
    details: dict[str, object] = Field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return (
            self.status in {AuditIssueStatus.OPEN, AuditIssueStatus.ACKNOWLEDGED}
            and self.severity in {AuditSeverity.BLOCKER, AuditSeverity.CRITICAL}
        )


class FinalReleaseCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: str = Field(min_length=1)
    passed: bool
    required: bool = True
    warning: bool = False
    evidence: list[str] = Field(default_factory=list)
    notes: str | None = None


class FinalReleaseChecklist(BaseModel):
    model_config = ConfigDict(extra='forbid')
    generated_at: datetime
    checks: list[FinalReleaseCheck] = Field(default_factory=list)
    readiness: FinalReleaseReadiness

    @model_validator(mode='after')
    def unique_categories(self) -> 'FinalReleaseChecklist':
        categories = [item.category for item in self.checks]
        if len(categories) != len(set(categories)):
            raise ValueError('final-release checklist categories must be unique')
        if self.readiness is FinalReleaseReadiness.READY and any(
            item.required and not item.passed for item in self.checks
        ):
            raise ValueError('READY is prohibited while a required check has failed')
        return self


class FinalReleaseReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1
    generated_at: datetime
    readiness: FinalReleaseReadiness
    checklist: FinalReleaseChecklist
    consistency_findings: list[ConsistencyFinding] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    final_author_approved: bool = False
    final_approval_by: str | None = None
    final_approval_at: datetime | None = None
    release_permitted: bool = False

    @model_validator(mode='after')
    def enforce_release_gate(self) -> 'FinalReleaseReport':
        if self.final_author_approved and (
            not self.final_approval_by or self.final_approval_at is None
        ):
            raise ValueError('final author approval requires approver and timestamp')
        allowed = self.readiness is FinalReleaseReadiness.READY or (
            self.readiness is FinalReleaseReadiness.READY_WITH_WARNINGS
            and self.final_author_approved
        )
        if self.release_permitted and not allowed:
            raise ValueError('release cannot be permitted for the reported readiness')
        return self


class ReleaseArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    role: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    release_path: str = Field(min_length=1)
    sha256: str
    size_bytes: int = Field(ge=0)
    approved: bool = True

    @field_validator('sha256')
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        value = value.lower()
        if not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('artifact hash must be lowercase SHA-256 hex')
        return value


class ReleaseManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: int = 1
    release_name: str
    created_at: datetime
    readiness: FinalReleaseReadiness
    final_author_approved: bool
    artifacts: list[ReleaseArtifact] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    immutable: bool = True

    @field_validator('release_name')
    @classmethod
    def valid_release_name(cls, value: str) -> str:
        if not re.fullmatch(r'release_v\d{3,}', value):
            raise ValueError('release_name must match release_v001')
        return value

    @model_validator(mode='after')
    def unique_artifacts(self) -> 'ReleaseManifest':
        paths = [item.release_path.casefold() for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError('release artifact paths must be unique')
        if any(not item.approved for item in self.artifacts):
            raise ValueError('release manifest cannot contain unapproved artifacts')
        return self
