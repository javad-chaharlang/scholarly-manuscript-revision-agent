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
from scholarly_revision.models.response_package import (
    CommentResolution, EditorCoverLetter, LocationStatus, ResponseEntry,
    ResponsePackage, ResponseStatus, ReviewerResponseSection,
)
from scholarly_revision.models.release import (
    ConsistencyCategory, ConsistencyFinding, FinalReleaseCheck,
    FinalReleaseChecklist, FinalReleaseReport, ManualVisualQAArtifactDecision,
    ManualVisualQADecision, ManualVisualQARecord, ReleaseArtifact,
    ReleaseManifest,
)

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
    'CommentResolution', 'EditorCoverLetter', 'LocationStatus', 'ResponseEntry',
    'ResponsePackage', 'ResponseStatus', 'ReviewerResponseSection',
    'ConsistencyCategory', 'ConsistencyFinding', 'FinalReleaseCheck',
    'FinalReleaseChecklist', 'FinalReleaseReport', 'ReleaseArtifact',
    'ReleaseManifest', 'ManualVisualQAArtifactDecision',
    'ManualVisualQADecision', 'ManualVisualQARecord',
]
from scholarly_revision.models.scientific_audit import (
    AuditIssue, AuditIssueStatus, AuditSeverity, CitationAuditResult,
    EquationSymbolAuditResult, FigureTableAuditResult, FinalReleaseReadiness,
    FrontMatterAuditResult, HighlightAuditResult, NumericalConsistencyResult,
    ReferenceAuditResult, ResultIntegrityResult, ScientificQAReport,
    TerminologyAuditResult,
)
__all__ += [
    'AuditIssue','AuditIssueStatus','AuditSeverity','CitationAuditResult',
    'EquationSymbolAuditResult','FigureTableAuditResult','FinalReleaseReadiness',
    'FrontMatterAuditResult','HighlightAuditResult','NumericalConsistencyResult',
    'ReferenceAuditResult','ResultIntegrityResult','ScientificQAReport',
    'TerminologyAuditResult',
]
