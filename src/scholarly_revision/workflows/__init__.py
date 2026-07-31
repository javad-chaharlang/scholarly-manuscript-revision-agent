'''Deterministic revision workflows.'''

from scholarly_revision.workflows.intake_workflow import (
    IntakeRequest,
    run_intake_workflow,
)

__all__ = ['IntakeRequest', 'run_intake_workflow']
from scholarly_revision.workflows.scientific_qa_workflow import (
    ScientificQAWorkflowResult, run_scientific_qa_workflow,
)
__all__ = [
    'ScientificQAWorkflowResult','run_scientific_qa_workflow',
]
