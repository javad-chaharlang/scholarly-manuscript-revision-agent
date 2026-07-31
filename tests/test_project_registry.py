from datetime import UTC, datetime
from pathlib import Path

import pytest

from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.config_loader import (
    load_project_manifest, save_project_manifest,
)
from scholarly_revision.services.project_registry import ProjectRegistry


ROOT = Path(__file__).resolve().parents[1]


def _project(workspace: Path) -> Path:
    project = workspace / 'synthetic-project'
    (project / 'config').mkdir(parents=True)
    manifest = load_project_manifest(ROOT / 'templates' / 'project_manifest.yaml')
    manifest = manifest.model_copy(update={
        'project_name': 'Synthetic project',
        'manuscript_id': 'SYNTHETIC-ID',
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC),
    })
    save_project_manifest(manifest, project / 'config' / 'project_manifest.yaml')
    return project


def test_registry_persists_and_resumes_outside_git(tmp_path: Path) -> None:
    workspace = tmp_path / 'private-workspace'
    project = _project(workspace)
    registry = ProjectRegistry(workspace)
    entry = registry.register(project, ProjectState.GAP_ANALYSIS_PENDING)
    assert registry.path.parent == workspace / '.scholarly_revision'
    assert entry.project_root == str(project.resolve())
    resumed = ProjectRegistry(workspace).get(entry.project_id)
    assert resumed.state is ProjectState.GAP_ANALYSIS_PENDING
    updated = registry.update_state(entry.project_id, ProjectState.PLAN_APPROVAL)
    assert updated.state is ProjectState.PLAN_APPROVAL


def test_registry_rejects_repository_workspace() -> None:
    with pytest.raises(ValueError, match='outside'):
        ProjectRegistry(ROOT)
