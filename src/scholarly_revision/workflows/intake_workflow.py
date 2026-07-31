'''Typed orchestration boundary for deterministic project intake.'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scholarly_revision.services.intake_service import (
    IntakeResult,
    create_revision_project,
)


@dataclass(frozen=True, slots=True)
class IntakeRequest:
    workspace_root: Path
    project_name: str
    manuscript_id: str
    reviewer_file: Path
    manuscript_file: Path | None = None
    journal: str | None = None
    reviewer_count: int | None = None
    force: bool = False


def run_intake_workflow(request: IntakeRequest) -> IntakeResult:
    '''Execute Phase 3 without network access or external model calls.'''

    return create_revision_project(
        workspace_root=request.workspace_root,
        project_name=request.project_name,
        manuscript_id=request.manuscript_id,
        reviewer_file=request.reviewer_file,
        manuscript_file=request.manuscript_file,
        journal=request.journal,
        reviewer_count=request.reviewer_count,
        force=request.force,
    )
