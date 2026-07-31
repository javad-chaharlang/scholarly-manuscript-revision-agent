from pathlib import Path

import pytest

from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.project_state_service import ProjectStateService


def test_state_transitions_block_resume_and_timeline(tmp_path: Path) -> None:
    root = tmp_path / 'project'
    (root / 'config').mkdir(parents=True)
    (root / 'audit').mkdir()
    service = ProjectStateService(root)
    record = service.initialize('synthetic-project', actor='tester')
    assert record.state is ProjectState.NEW
    record = service.transition(
        ProjectState.INTAKE_PENDING, action='begin', actor='tester',
    )
    assert record.state is ProjectState.INTAKE_PENDING
    with pytest.raises(ValueError, match='invalid project transition'):
        service.transition(ProjectState.RELEASED, action='skip', actor='tester')
    blocked = service.block(
        ['Synthetic missing input'], action='check', actor='tester',
    )
    assert blocked.blocked_from is ProjectState.INTAKE_PENDING
    resumed = service.transition(
        ProjectState.INTAKE_PENDING, action='resume', actor='tester',
    )
    assert resumed.state is ProjectState.INTAKE_PENDING
    timeline = service.timeline()
    assert [item.sequence for item in timeline] == list(range(len(timeline)))
    assert timeline[-1].to_state is ProjectState.INTAKE_PENDING


def test_audit_details_reject_confidential_content_keys(tmp_path: Path) -> None:
    root = tmp_path / 'project'
    (root / 'config').mkdir(parents=True)
    (root / 'audit').mkdir()
    service = ProjectStateService(root)
    service.initialize('synthetic-project')
    with pytest.raises(ValueError, match='confidentiality-safe'):
        service.record_event(
            event_type='BAD', action='bad', actor='tester',
            details={'manuscript_text': 'not written'},
        )
