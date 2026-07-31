'''Deterministic revision workflows.'''

from scholarly_revision.workflows.intake_workflow import (
    IntakeRequest,
    run_intake_workflow,
)

__all__ = ['IntakeRequest', 'run_intake_workflow']
from scholarly_revision.workflows.scientific_qa_workflow import (
    ScientificQAWorkflowResult, run_scientific_qa_workflow,
)
__all__ += [
    'ScientificQAWorkflowResult','run_scientific_qa_workflow',
]
from scholarly_revision.workflows.finalization_workflow import (
    build_submission_package, generate_response_letter, prepare_response_drafts,
    run_final_consistency_check, verify_response_letter,
)
__all__ += [
    'build_submission_package', 'generate_response_letter',
    'prepare_response_drafts', 'run_final_consistency_check',
    'verify_response_letter',
]
