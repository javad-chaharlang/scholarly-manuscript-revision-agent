'''Core domain models for scholarly manuscript revision.'''

from scholarly_revision.models import (
    EvidenceRecord,
    ExperimentalResultRecord,
    ProjectManifest,
    QAFinding,
    ReferenceRecord,
    ResponseLetterEntry,
    ReviewerComment,
    RevisionAction,
    RevisionDraft,
    RevisionTextDecisionRecord,
    TraceabilityRecord,
)

__all__ = [
    'EvidenceRecord',
    'ExperimentalResultRecord',
    'ProjectManifest',
    'QAFinding',
    'ReferenceRecord',
    'ResponseLetterEntry',
    'ReviewerComment',
    'RevisionAction',
    'RevisionDraft',
    'RevisionTextDecisionRecord',
    'TraceabilityRecord',
]

__version__ = '0.2.0'
