'''Safe project metadata and deterministic project policy.'''

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import HighlightColor, ResultStatus


_PROHIBITED_FIELD_PATTERN = re.compile(
    r'(?:^|_)(?:api_?key|password|passwd|token|secret|credential|private_?key)(?:$|_)',
    re.IGNORECASE,
)
_MANUSCRIPT_CONTENT_FIELDS = {
    'actual_manuscript_content',
    'full_manuscript_text',
    'manuscript_content',
    'manuscript_text',
}


def _check_mapping_keys(value: Any, location: str = 'manifest') -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower().replace('-', '_')
            if _PROHIBITED_FIELD_PATTERN.search(normalized_key):
                raise ValueError(f'prohibited secret-like field at {location}.{key}')
            if normalized_key in _MANUSCRIPT_CONTENT_FIELDS:
                raise ValueError(
                    f'actual manuscript content is not permitted at {location}.{key}'
                )
            _check_mapping_keys(nested_value, f'{location}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_mapping_keys(item, f'{location}[{index}]')


class HighlightPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reviewer_1: HighlightColor = HighlightColor.YELLOW
    reviewer_2: HighlightColor = HighlightColor.BRIGHT_GREEN
    shared_and_general: HighlightColor = HighlightColor.VIOLET

    @model_validator(mode='after')
    def enforce_repository_policy(self) -> HighlightPolicy:
        required = (
            (self.reviewer_1, HighlightColor.YELLOW, 'reviewer_1'),
            (self.reviewer_2, HighlightColor.BRIGHT_GREEN, 'reviewer_2'),
            (
                self.shared_and_general,
                HighlightColor.VIOLET,
                'shared_and_general',
            ),
        )
        for actual, expected, field_name in required:
            if actual is not expected:
                raise ValueError(f'{field_name} must be {expected.value}')
        return self


class ApprovalGates(BaseModel):
    model_config = ConfigDict(extra='forbid')

    revision_plan: bool = True
    novelty_claims: bool = True
    experimental_conclusions: bool = True
    statistical_interpretations: bool = True
    rejected_reviewer_requests: bool = True
    final_release: bool = True


class InputFiles(BaseModel):
    '''File identities only; manuscript or reviewer contents are never stored here.'''

    model_config = ConfigDict(extra='forbid')

    manuscript: str | None = None
    reviewer_comments: list[str] = Field(default_factory=list)
    journal_instructions: str | None = None
    reference_sources: list[str] = Field(default_factory=list)
    experimental_records: list[str] = Field(default_factory=list)
    prior_round_materials: list[str] = Field(default_factory=list)
    editor_letter: str | None = None
    result_registry: str | None = None
    reference_registry: str | None = None
    response_sample: str | None = None


class OutputNames(BaseModel):
    model_config = ConfigDict(extra='forbid')

    highlighted_manuscript: str
    clean_manuscript: str
    revision_workbook: str
    response_letter: str
    qa_report: str
    audit_log: str

    @field_validator('*')
    @classmethod
    def reject_absolute_paths(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError('output file names must not be empty')
        if '\x00' in value:
            raise ValueError('output file names must not contain null bytes')
        if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
            raise ValueError('output file names must not contain absolute paths')
        return value


class ProjectManifest(BaseModel):
    '''Non-confidential metadata governing one revision project.'''

    model_config = ConfigDict(extra='forbid', validate_assignment=True)

    project_name: str = Field(min_length=1)
    manuscript_id: str = Field(min_length=1)
    manuscript_title: str = Field(default='UNSPECIFIED', min_length=1)
    journal: str = Field(min_length=1)
    revision_round: int = Field(ge=1)
    manuscript_language: str = Field(min_length=1)
    response_language: str = Field(min_length=1)
    citation_style: str = Field(min_length=1)
    reviewer_count: int = Field(ge=1)
    result_status: ResultStatus
    highlight_policy: HighlightPolicy = Field(default_factory=HighlightPolicy)
    approval_gates: ApprovalGates = Field(default_factory=ApprovalGates)
    input_files: InputFiles = Field(default_factory=InputFiles)
    output_names: OutputNames
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode='before')
    @classmethod
    def reject_confidential_or_secret_fields(cls, value: Any) -> Any:
        _check_mapping_keys(value)
        return value

    @model_validator(mode='after')
    def validate_timestamp_order(self) -> ProjectManifest:
        if self.created_at and self.updated_at and self.updated_at < self.created_at:
            raise ValueError('updated_at cannot precede created_at')
        return self
