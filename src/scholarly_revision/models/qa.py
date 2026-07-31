'''Quality-assurance findings for deterministic and visual checks.'''

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QAStringEnum(str, Enum):
    '''String enum used in QA schema output.'''


class QACategory(QAStringEnum):
    FRONT_MATTER = 'FRONT_MATTER'
    HEADINGS = 'HEADINGS'
    FIGURES = 'FIGURES'
    TABLES = 'TABLES'
    EQUATIONS = 'EQUATIONS'
    CITATIONS = 'CITATIONS'
    REFERENCES = 'REFERENCES'
    NUMERICAL_CONSISTENCY = 'NUMERICAL_CONSISTENCY'
    HIGHLIGHTS = 'HIGHLIGHTS'
    PAGE_LAYOUT = 'PAGE_LAYOUT'
    RESPONSE_LETTER_CONSISTENCY = 'RESPONSE_LETTER_CONSISTENCY'
    CONFIDENTIALITY = 'CONFIDENTIALITY'


class QASeverity(QAStringEnum):
    CRITICAL = 'CRITICAL'
    MAJOR = 'MAJOR'
    MINOR = 'MINOR'
    INFORMATIONAL = 'INFORMATIONAL'


class QAStatus(QAStringEnum):
    OPEN = 'OPEN'
    RESOLVED = 'RESOLVED'
    VERIFIED = 'VERIFIED'
    WAIVED = 'WAIVED'


class QAFinding(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    finding_id: str = Field(min_length=1)
    category: QACategory
    severity: QASeverity
    description: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    object_id: str | None = None
    status: QAStatus = QAStatus.OPEN
    resolution: str | None = None
    verified: bool = False

    @model_validator(mode='after')
    def validate_resolution_state(self) -> QAFinding:
        if self.verified:
            if self.status is not QAStatus.VERIFIED:
                raise ValueError('verified findings must have VERIFIED status')
            if not self.resolution or not self.resolution.strip():
                raise ValueError('verified findings require a resolution')
        return self
