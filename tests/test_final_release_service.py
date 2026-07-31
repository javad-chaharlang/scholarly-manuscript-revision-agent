from pathlib import Path

from phase7_helpers import make_ready_phase7_project
from scholarly_revision.models.release import ConsistencyFinding
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.final_release_service import evaluate_final_release


def test_ready_and_blocker_logic(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    assert evaluate_final_release(root).readiness.value == 'READY'
    blocker = ConsistencyFinding(
        finding_id='CONS-X', category='CHANGE_CLAIM', severity='BLOCKER',
        description='False claimed revision.',
    )
    assert evaluate_final_release(root, [blocker]).readiness.value == 'BLOCKED'


def test_ready_with_warnings_requires_explicit_approval(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    warning = ConsistencyFinding(
        finding_id='CONS-W', category='ARTIFACT', severity='MINOR',
        description='Anonymous non-blocking warning.',
    )
    approved = {
        'approved': True, 'decision_maker': 'anonymous-author',
        'decision_timestamp': '2030-01-01T00:00:00Z',
    }
    report = evaluate_final_release(root, [warning], final_approval=approved)
    assert report.readiness.value == 'READY_WITH_WARNINGS'
    assert report.release_permitted


def test_missing_visual_rendering_records_manual_qa_gate(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    visual_path = root / 'audit' / 'visual_inspection.json'
    visual_path.unlink()
    (root / 'audit' / 'manual_visual_qa_decisions.json').unlink()
    report = evaluate_final_release(root)
    visual = read_json(visual_path)
    assert report.readiness.value == 'NOT_READY'
    assert not report.release_permitted
    assert visual['status'] == 'MANUAL_VISUAL_QA_REQUIRED'
    assert visual['passed'] is False
    check = next(
        item for item in report.checklist.checks
        if item.category == 'rendered Word documents visually inspected'
    )
    assert check.notes == 'MANUAL_VISUAL_QA_REQUIRED'
