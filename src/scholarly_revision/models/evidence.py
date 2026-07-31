'''Evidence and experimental-result records.'''

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import EvidenceStatus, ResultStatus
from scholarly_revision.models.reviewer import _validated_comment_id


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    evidence_id: str = Field(min_length=1)
    evidence_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_path: str | None = None
    source_description: str = Field(min_length=1)
    related_comment_ids: list[str] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.PROVIDED
    verified_by: str | None = None
    verified_at: datetime | None = None
    notes: str | None = None

    @field_validator('related_comment_ids')
    @classmethod
    def validate_related_comment_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        return values

    @model_validator(mode='after')
    def validate_verification(self) -> EvidenceRecord:
        if self.status is EvidenceStatus.VERIFIED:
            if not self.verified_by or not self.verified_by.strip():
                raise ValueError('VERIFIED evidence requires verified_by')
            if self.verified_at is None:
                raise ValueError('VERIFIED evidence requires verified_at')
        return self


class ExperimentalResultRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    result_id: str = Field(min_length=1)
    metric_name: str | None = None
    value: Decimal | str | None = None
    unit: str | None = None
    dataset: str | None = None
    configuration: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_cell_or_range: str | None = None
    result_status: ResultStatus = ResultStatus.DRAFT
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_REQUIRED
    recomputed: bool = False
    verification_notes: str | None = None
    used_in_sections: list[str] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def require_metric_for_numeric_value(cls, value: object) -> object:
        if isinstance(value, dict):
            supplied_value = value.get('value')
            metric_name = value.get('metric_name')
            if (
                isinstance(supplied_value, (int, float, Decimal))
                and not isinstance(supplied_value, bool)
                and (not isinstance(metric_name, str) or not metric_name.strip())
            ):
                raise ValueError('numeric values require metric_name')
        return value

    @field_validator('metric_name')
    @classmethod
    def reject_blank_metric_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError('metric_name must be non-empty when provided')
        return value

    @model_validator(mode='after')
    def validate_final_result(self) -> ExperimentalResultRecord:
        if self.result_status is ResultStatus.FINAL:
            if self.evidence_status is not EvidenceStatus.VERIFIED:
                raise ValueError('FINAL results require VERIFIED source evidence')
            if not self.source_file or not self.source_file.strip():
                raise ValueError('FINAL results require a source_file')
        return self
