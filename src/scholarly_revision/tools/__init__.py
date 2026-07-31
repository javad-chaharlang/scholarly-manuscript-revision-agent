'''Deterministic local file-processing tools.'''

from scholarly_revision.tools.docx_reader import DocxReadError, DocxRecord, read_docx
from scholarly_revision.tools.reviewer_parser import (
    ReviewerParseError,
    ReviewerParseResult,
    parse_reviewer_comments,
)
from scholarly_revision.tools.workbook_builder import (
    REVISION_WORKBOOK_SHEETS,
    build_revision_workbook,
)

__all__ = [
    'DocxReadError',
    'DocxRecord',
    'REVISION_WORKBOOK_SHEETS',
    'ReviewerParseError',
    'ReviewerParseResult',
    'build_revision_workbook',
    'parse_reviewer_comments',
    'read_docx',
]
from scholarly_revision.tools.citation_auditor import audit_citations, parse_citation_group
from scholarly_revision.tools.reference_auditor import audit_references
from scholarly_revision.tools.numerical_consistency_auditor import audit_numerical_consistency
from scholarly_revision.tools.result_integrity_auditor import audit_result_integrity
from scholarly_revision.tools.figure_table_auditor import audit_figures_tables
from scholarly_revision.tools.equation_symbol_auditor import audit_equations_symbols
from scholarly_revision.tools.terminology_auditor import audit_terminology
from scholarly_revision.tools.highlight_auditor import audit_highlights
from scholarly_revision.tools.front_matter_auditor import audit_front_matter
__all__ += [
    'audit_citations','parse_citation_group','audit_references',
    'audit_numerical_consistency','audit_result_integrity','audit_figures_tables',
    'audit_equations_symbols','audit_terminology','audit_highlights','audit_front_matter',
]
