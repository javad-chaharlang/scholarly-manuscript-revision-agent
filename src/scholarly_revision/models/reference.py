'''Reference identity and bibliographic verification records.'''

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholarly_revision.models.enums import HighlightColor
from scholarly_revision.models.reviewer import (
    _apply_or_check_highlight,
    _highlight_for_action_ids,
    _validated_comment_id,
)


class ReferenceRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    reference_id: str = Field(min_length=1)
    temporary_number: int | None = None
    final_number: int | None = Field(default=None, ge=1)
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal_or_source: str | None = None
    doi: str | None = None
    url: str | None = None
    reason_added: str = Field(min_length=1)
    requested_by_comment_ids: list[str] = Field(default_factory=list)
    first_citation_location: str | None = None
    endnote_verified: bool = False
    bibliographic_verified: bool = False
    highlight: HighlightColor | None = None
    notes: str | None = None

    @model_validator(mode='before')
    @classmethod
    def assign_policy_highlight(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_ids = data.get('requested_by_comment_ids') or []
        if isinstance(raw_ids, (str, bytes)):
            return data
        expected = (
            _highlight_for_action_ids(list(raw_ids))
            if raw_ids
            else HighlightColor.VIOLET
        )
        return _apply_or_check_highlight(data, expected)

    @field_validator('requested_by_comment_ids')
    @classmethod
    def validate_requested_by_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _validated_comment_id(value)
        return values

    @field_validator('authors')
    @classmethod
    def reject_blank_authors(cls, values: list[str]) -> list[str]:
        if any(not author.strip() for author in values):
            raise ValueError('authors must not contain blank values')
        return values

    @field_validator('doi')
    @classmethod
    def normalize_absent_doi(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError('doi must be omitted rather than blank')
        return value

    @model_validator(mode='after')
    def validate_bibliographic_verification(self) -> ReferenceRecord:
        if self.bibliographic_verified:
            if not self.title or not self.title.strip() or not self.authors:
                raise ValueError(
                    'bibliographic_verified requires both title and authors'
                )
        return self
