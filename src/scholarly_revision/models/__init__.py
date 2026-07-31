'''Validated domain records used by the revision source of truth.'''

from scholarly_revision.models.evidence import EvidenceRecord, ExperimentalResultRecord
from scholarly_revision.models.gap_analysis import (
    ActionProposal,
    ApprovalRecord,
    GapAnalysisAssessment,
    ManuscriptEvidence,
)
from scholarly_revision.models.project import ProjectManifest
from scholarly_revision.models.qa import QAFinding
from scholarly_revision.models.reference import ReferenceRecord
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.revision_draft import (
    ChangeRecord,
    DocumentVersionRecord,
    RevisionDraft,
    RevisionTextDecisionRecord,
)
from scholarly_revision.models.traceability import ResponseLetterEntry, TraceabilityRecord

__all__ = [
    'ActionProposal',
    'ApprovalRecord',
    'ChangeRecord',
    'DocumentVersionRecord',
    'RevisionDraft',
    'RevisionTextDecisionRecord',
    'EvidenceRecord',
    'ExperimentalResultRecord',
    'ProjectManifest',
    'GapAnalysisAssessment',
    'ManuscriptEvidence',
    'QAFinding',
    'ReferenceRecord',
    'ResponseLetterEntry',
    'ReviewerComment',
    'RevisionAction',
    'TraceabilityRecord',
]
