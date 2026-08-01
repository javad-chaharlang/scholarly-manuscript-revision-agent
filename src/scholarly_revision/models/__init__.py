'''Validated domain records used by the revision source of truth.'''

from scholarly_revision.models.evidence import EvidenceRecord, ExperimentalResultRecord
from scholarly_revision.models.gap_analysis import (
    ActionProposal,
    ApprovalRecord,
    GapAnalysisAssessment,
    ManuscriptEvidence,
)
from scholarly_revision.models.project import ProjectManifest
from scholarly_revision.models.project_state import (
    ProjectAuditEvent, ProjectRegistryEntry, ProjectRegistryFile,
    ProjectState, ProjectStateRecord,
)
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
from scholarly_revision.models.agent_context import (
    AgentContextManifest, ContextManuscriptSection, ContextPolicy,
    ContextReviewerComment,
)
from scholarly_revision.models.agent_run import (
    AgentAuthorDecision, AgentRun, AgentRunStatus,
)
from scholarly_revision.models.agent_task import (
    AgentTask, AgentTaskPriority, AgentTaskStatus, AgentTaskType,
    TransmissionDecision,
)
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
    'AgentAuthorDecision', 'AgentContextManifest', 'AgentRun', 'AgentRunStatus',
    'AgentTask', 'AgentTaskPriority', 'AgentTaskStatus', 'AgentTaskType',
    'ContextManuscriptSection', 'ContextPolicy', 'ContextReviewerComment',
    'TransmissionDecision',
    'ActionProposal',
    'ApprovalRecord',
    'ChangeRecord',
    'DocumentVersionRecord',
    'RevisionDraft',
    'RevisionTextDecisionRecord',
    'EvidenceRecord',
    'ExperimentalResultRecord',
    'ProjectManifest',
    'ProjectAuditEvent',
    'ProjectRegistryEntry',
    'ProjectRegistryFile',
    'ProjectState',
    'ProjectStateRecord',
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
