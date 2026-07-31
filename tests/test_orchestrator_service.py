from hashlib import sha256
from pathlib import Path

import pytest

from scholarly_revision.services.orchestrator_service import (
    NewProjectRequest, OrchestratorService,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'


def test_synthetic_creation_resume_invalid_actions_and_privacy(tmp_path: Path) -> None:
    workspace = tmp_path / 'private-workspace'
    reviewer = FIXTURES / 'synthetic_reviewer_comments.docx'
    manuscript = FIXTURES / 'synthetic_manuscript.docx'
    source_hashes = {
        reviewer: sha256(reviewer.read_bytes()).hexdigest(),
        manuscript: sha256(manuscript.read_bytes()).hexdigest(),
    }
    orchestrator = OrchestratorService(workspace)
    state = orchestrator.create_project(
        NewProjectRequest(
            workspace_root=workspace,
            project_name='Synthetic phase eight',
            manuscript_id='SYNTHETIC-P8',
            manuscript_title='Anonymous Synthetic Study',
            journal='Synthetic Journal',
            revision_round=2,
            reviewer_count=2,
            manuscript_language='English',
            response_language='English',
            citation_style='numeric',
            result_status='DRAFT',
            reviewer_file=reviewer,
            manuscript_file=manuscript,
            result_registry=FIXTURES / 'synthetic_results_registry.json',
            reference_registry=FIXTURES / 'synthetic_reference_registry.json',
        ),
        actor='Synthetic Author',
    )
    entry = orchestrator.registry.get(state.project_id)
    project_root = Path(entry.project_root)
    assert ROOT not in project_root.parents
    assert project_root.is_dir()
    assert OrchestratorService(workspace).resume(state.project_id).state is state.state
    assert not orchestrator.available_actions(project_root)['apply_revisions']
    with pytest.raises(ValueError, match='invalid'):
        orchestrator.apply_revisions(project_root, actor='Synthetic Author')
    dashboard = orchestrator.dashboard(project_root)
    assert dashboard['total_comments'] > 0
    assert dashboard['project_status'] == state.state.value
    assert (workspace / '.scholarly_revision' / 'registry.json').is_file()
    for path, expected in source_hashes.items():
        assert sha256(path.read_bytes()).hexdigest() == expected


def test_new_project_requires_docx_manuscript(tmp_path: Path) -> None:
    bad = tmp_path / 'manuscript.pdf'
    bad.write_bytes(b'%PDF-synthetic')
    request = NewProjectRequest(
        workspace_root=tmp_path / 'workspace',
        project_name='Synthetic',
        manuscript_id='SYN',
        manuscript_title='Synthetic',
        journal='Synthetic',
        revision_round=1,
        reviewer_count=1,
        manuscript_language='English',
        response_language='English',
        citation_style='numeric',
        result_status='DRAFT',
        reviewer_file=FIXTURES / 'synthetic_reviewer_comments.docx',
        manuscript_file=bad,
    )
    with pytest.raises(ValueError, match='DOCX'):
        OrchestratorService.validate_new_project(request)
