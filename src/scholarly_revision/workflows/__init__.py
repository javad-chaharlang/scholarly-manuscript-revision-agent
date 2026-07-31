'''Deterministic revision workflows.'''

from scholarly_revision.workflows.intake_workflow import (
    IntakeRequest,
    run_intake_workflow,
)

__all__ = ['IntakeRequest', 'run_intake_workflow']
