from pathlib import Path

import pytest
from pydantic import ValidationError

from phase7_helpers import (
    approved_manual_visual_qa_payload, make_ready_phase7_project,
)
from scholarly_revision.models.release import MANUAL_VISUAL_QA_ARTIFACTS
from scholarly_revision.services.final_release_service import evaluate_final_release
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.manual_visual_qa_service import (
    evaluate_manual_visual_qa, import_manual_visual_qa_decisions,
    prepare_manual_visual_qa_template,
)


def test_prepare_template_does_not_infer_decisions(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    path = prepare_manual_visual_qa_template(root)
    payload = read_json(path)
    assert [item['artifact_name'] for item in payload['decisions']] == list(
        MANUAL_VISUAL_QA_ARTIFACTS
    )
    assert all(item['decision'] == '' for item in payload['decisions'])
    assert all(item['opened_successfully'] is None for item in payload['decisions'])
    with pytest.raises(FileExistsError, match='already exists'):
        prepare_manual_visual_qa_template(root)


def test_approved_requires_every_check_to_pass(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    payload = approved_manual_visual_qa_payload(root)
    payload['decisions'][0]['repair_warning_present'] = True
    with pytest.raises(ValidationError, match='failed checks'):
        import_manual_visual_qa_decisions(root, payload)


def test_rejected_decision_keeps_manual_gate_unresolved(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    payload = approved_manual_visual_qa_payload(root)
    payload['decisions'][0]['decision'] = 'REJECTED'
    import_manual_visual_qa_decisions(root, payload)
    evaluation = evaluate_manual_visual_qa(root)
    report = evaluate_final_release(root)
    assert not evaluation.passed
    assert 'REJECTED' in evaluation.reason
    assert report.readiness.value == 'NOT_READY'
    assert not report.release_permitted
    assert read_json(root / 'audit' / 'visual_inspection.json')['status'] == (
        'MANUAL_VISUAL_QA_REQUIRED'
    )


def test_artifact_change_invalidates_imported_approval(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    response = root / 'outputs' / 'Response_to_Reviewers.docx'
    response.write_bytes(response.read_bytes() + b'changed-after-approval')
    evaluation = evaluate_manual_visual_qa(root)
    assert not evaluation.passed
    assert 'stale for Response_to_Reviewers.docx' in evaluation.reason


def test_incomplete_artifact_scope_is_rejected(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    payload = approved_manual_visual_qa_payload(root)
    payload['decisions'].pop()
    with pytest.raises(ValidationError, match='cover exactly'):
        import_manual_visual_qa_decisions(root, payload)
