'''Validated records for deterministic Phase 6 scientific quality assurance.'''
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class AuditStringEnum(str, Enum):
    '''String enum with stable JSON values.'''

class AuditSeverity(AuditStringEnum):
    BLOCKER='BLOCKER'; CRITICAL='CRITICAL'; MAJOR='MAJOR'; MINOR='MINOR'; INFORMATIONAL='INFORMATIONAL'

class AuditIssueStatus(AuditStringEnum):
    OPEN='OPEN'; ACKNOWLEDGED='ACKNOWLEDGED'; RESOLVED='RESOLVED'; ACCEPTED_RISK='ACCEPTED_RISK'; NOT_APPLICABLE='NOT_APPLICABLE'

class FinalReleaseReadiness(AuditStringEnum):
    BLOCKED='BLOCKED'; NOT_READY='NOT_READY'; READY_WITH_WARNINGS='READY_WITH_WARNINGS'; READY='READY'

class AuditIssue(BaseModel):
    model_config=ConfigDict(extra='forbid', validate_assignment=True)
    issue_id: str=Field(min_length=1)
    category: str=Field(min_length=1)
    severity: AuditSeverity
    description: str=Field(min_length=1)
    document_element_id: str|None=None
    section: str|None=None
    evidence: list[str]=Field(default_factory=list)
    related_comment_ids: list[str]=Field(default_factory=list)
    related_action_ids: list[str]=Field(default_factory=list)
    status: AuditIssueStatus=AuditIssueStatus.OPEN
    resolution_required: bool=True
    resolution: str|None=None
    verified_by: str|None=None
    verified_at: datetime|None=None
    manual_review_required: bool=False

    @field_validator('evidence','related_comment_ids','related_action_ids')
    @classmethod
    def reject_blank_list_values(cls, values:list[str])->list[str]:
        if any(not str(item).strip() for item in values):
            raise ValueError('audit identifier and evidence lists cannot contain blanks')
        return list(dict.fromkeys(values))

    @model_validator(mode='after')
    def validate_resolution(self)->'AuditIssue':
        if self.status is AuditIssueStatus.RESOLVED and not (self.resolution or '').strip():
            raise ValueError('RESOLVED issues require a resolution description')
        if self.status is AuditIssueStatus.ACCEPTED_RISK and not (self.resolution or '').strip():
            raise ValueError('ACCEPTED_RISK issues require a justification')
        if self.verified_at is not None and not self.verified_by:
            raise ValueError('verified_at requires verified_by')
        return self

    @property
    def unresolved(self)->bool:
        return self.status in {AuditIssueStatus.OPEN,AuditIssueStatus.ACKNOWLEDGED}

class CitationOccurrence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    exact_text:str
    normalized_numbers:list[int]=Field(default_factory=list)
    document_element_id:str
    section:str|None=None
    structural_context:str
    order_index:int
    endnote_field_code:bool=False

class BibliographyEntry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    number:int|None=None
    exact_text:str
    document_element_id:str
    title_candidate:str|None=None
    author_candidate:str|None=None
    year_candidate:int|None=None
    source_candidate:str|None=None
    doi_like_strings:list[str]=Field(default_factory=list)
    highlight_colors:list[str]=Field(default_factory=list)

class NumericalCandidate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    candidate_id:str
    metric_name:str|None=None
    value:Decimal|str
    unit:str|None=None
    section:str|None=None
    source_element:str
    surrounding_context:str
    dataset:str|None=None
    configuration:str|None=None
    result_registry_link:str|None=None
    value_kind:str='NUMBER'
    verification_status:str|None=None

class BaseAuditResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    category:str
    issues:list[AuditIssue]=Field(default_factory=list)
    checked_element_count:int=0
    manual_review_required:bool=False

class CitationAuditResult(BaseAuditResult):
    category:str='CITATION'
    occurrences:list[CitationOccurrence]=Field(default_factory=list)
    cited_reference_numbers:list[int]=Field(default_factory=list)
    bibliography_count:int=0

class ReferenceAuditResult(BaseAuditResult):
    category:str='REFERENCE'
    entries:list[BibliographyEntry]=Field(default_factory=list)
    total_reference_count:int=0
    numbering_sequence:list[int]=Field(default_factory=list)
    structural_validation_complete:bool=True
    bibliographic_verification_performed:bool=False

class NumericalConsistencyResult(BaseAuditResult):
    category:str='NUMERICAL_CONSISTENCY'
    candidates:list[NumericalCandidate]=Field(default_factory=list)
    mathematical_checks_performed:list[str]=Field(default_factory=list)
    scientific_verification_performed:bool=False

class ResultIntegrityResult(BaseAuditResult):
    category:str='RESULT_INTEGRITY'
    manuscript_result_ids:list[str]=Field(default_factory=list)
    registry_result_ids:list[str]=Field(default_factory=list)
    evidence_integrity_issue_ids:list[str]=Field(default_factory=list)

class FigureTableAuditResult(BaseAuditResult):
    category:str='FIGURE_TABLE'
    figures_detected:list[str]=Field(default_factory=list)
    tables_detected:list[str]=Field(default_factory=list)
    textual_checks_complete:bool=True
    visual_layout_checked:bool=False

class EquationSymbolAuditResult(BaseAuditResult):
    category:str='EQUATION_SYMBOL'
    equation_numbers:list[int]=Field(default_factory=list)
    symbols_detected:list[str]=Field(default_factory=list)
    mathematical_correctness_checked:bool=False

class TerminologyAuditResult(BaseAuditResult):
    category:str='TERMINOLOGY'
    term_frequencies:dict[str,dict[str,int]]=Field(default_factory=dict)
    locations:dict[str,list[str]]=Field(default_factory=dict)

class HighlightAuditResult(BaseAuditResult):
    category:str='HIGHLIGHT'
    highlighted_system_run_count:int=0
    clean_system_run_count:int=0
    text_equivalent:bool=False
    unrelated_author_highlights_preserved:bool=True

class FrontMatterAuditResult(BaseAuditResult):
    category:str='FRONT_MATTER'
    inspected_headers:int=0
    inspected_footers:int=0
    placeholder_patterns_checked:list[str]=Field(default_factory=list)

class ScientificQAReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:int=1
    generated_at:datetime
    source_hashes:dict[str,str]=Field(default_factory=dict)
    issues:list[AuditIssue]=Field(default_factory=list)
    total_issues:int=0
    count_by_category:dict[str,int]=Field(default_factory=dict)
    count_by_severity:dict[str,int]=Field(default_factory=dict)
    count_by_status:dict[str,int]=Field(default_factory=dict)
    blocker_count:int=0
    unresolved_critical_issues:int=0
    manual_review_count:int=0
    final_release_readiness:FinalReleaseReadiness
    evidence_dependent_issue_ids:list[str]=Field(default_factory=list)
    affected_sections:list[str]=Field(default_factory=list)
    affected_objects:list[str]=Field(default_factory=list)
    auditor_summaries:dict[str,dict[str,Any]]=Field(default_factory=dict)
    manuscript_modified:bool=False
    external_verification_performed:bool=False
    final_human_approval_recorded:bool=False

def issue(issue_id:str,category:str,severity:AuditSeverity|str,description:str,*,
          element_id:str|None=None,section:str|None=None,evidence:list[str]|None=None,
          related_comment_ids:list[str]|None=None,related_action_ids:list[str]|None=None,
          resolution_required:bool=True,manual:bool=False)->AuditIssue:
    return AuditIssue(issue_id=issue_id,category=category,severity=severity,
        description=description,document_element_id=element_id,section=section,
        evidence=evidence or [],related_comment_ids=related_comment_ids or [],
        related_action_ids=related_action_ids or [],resolution_required=resolution_required,
        manual_review_required=manual)
