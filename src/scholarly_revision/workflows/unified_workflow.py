'''Phase 8 public workflow boundary for local application and UI callers.'''

from __future__ import annotations

from pathlib import Path
from typing import Any

from scholarly_revision.models.project_state import ProjectStateRecord
from scholarly_revision.services.orchestrator_service import (
    NewProjectRequest, OrchestratorService,
)


class UnifiedProjectWorkflow:
    '''Small public facade that keeps presentation code out of workflow logic.'''

    def __init__(self, workspace_root: str | Path) -> None:
        self.orchestrator = OrchestratorService(workspace_root)

    def create(self, request: NewProjectRequest, *, actor: str) -> ProjectStateRecord:
        return self.orchestrator.create_project(request, actor=actor)

    def resume(self, project_id: str) -> ProjectStateRecord:
        return self.orchestrator.resume(project_id)

    def projects(self):
        return self.orchestrator.registry.list_projects()

    def status(self, project_root: str | Path) -> dict[str, Any]:
        return self.orchestrator.dashboard(project_root)

    def allowed_actions(self, project_root: str | Path) -> dict[str, bool]:
        return self.orchestrator.available_actions(project_root)


def open_unified_workflow(workspace_root: str | Path) -> UnifiedProjectWorkflow:
    return UnifiedProjectWorkflow(workspace_root)
