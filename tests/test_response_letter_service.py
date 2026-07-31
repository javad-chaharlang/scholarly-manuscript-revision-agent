from pathlib import Path

import pytest

from phase5_helpers import MANUSCRIPT, setup_approved_project
from phase7_helpers import make_ready_phase7_project
from scholarly_revision.workflows.revision_execution_workflow import apply_approved_revisions
from scholarly_revision.services.gap_analysis_service import write_json
from scholarly_revision.services.response_letter_service import (
    build_response_drafting_package, import_response_draft,
)


def test_drafting_package_preserves_exact_comment_and_blank_prose(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    package = build_response_drafting_package(root)
    assert package['entries'][0]['exact_comment'] == (
        'Please clarify the anonymous fixture scope.'
    )
    assert package['entries'][0]['author_response'] == ''
    assert package['scientific_prose_generated_by_deterministic_code'] is False


def test_missing_unknown_altered_and_false_claim_rejected(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    package = build_response_drafting_package(root)
    bad = root / 'working' / 'bad_response.json'
    write_json(bad, {'entries': []})
    with pytest.raises(ValueError, match='missing response'):
        import_response_draft(root, bad)
    package['entries'][0]['comment_id'] = 'R2-C01'
    write_json(bad, package)
    with pytest.raises(ValueError, match='unknown response'):
        import_response_draft(root, bad)
    package = build_response_drafting_package(root)
    package['entries'][0]['exact_comment'] = 'Altered.'
    write_json(bad, package)
    with pytest.raises(ValueError, match='altered'):
        import_response_draft(root, bad)
    package = build_response_drafting_package(root)
    package['entries'][0]['changes_made'] = 'A revision was completed.'
    write_json(bad, package)
    with pytest.raises(ValueError, match='ChangeLog IDs'):
        import_response_draft(root, bad)


def test_shared_action_context_and_strict_registry_rejections(tmp_path: Path) -> None:
    root = setup_approved_project(tmp_path)
    apply_approved_revisions(root, MANUSCRIPT)
    package = build_response_drafting_package(root)
    entries = {item['comment_id']: item for item in package['entries']}
    assert 'ACT-0006' in entries['R1-C01']['related_action_ids']
    assert 'ACT-0006' in entries['R2-C01']['related_action_ids']
    assert 'CHG-0006' in entries['R1-C01']['related_change_ids']
    assert entries['R1-C01']['highlight'] == 'YELLOW'
    assert entries['R2-C01']['highlight'] == 'BRIGHT_GREEN'

    bad = root / 'working' / 'bad_registry_response.json'
    entries['R1-C01']['related_change_ids'] = ['CHG-404']
    write_json(bad, package)
    with pytest.raises(ValueError, match='invalid ChangeLog'):
        import_response_draft(root, bad)
    package = build_response_drafting_package(root)
    package['entries'][0]['related_evidence_ids'] = ['EVIDENCE-404']
    package['entries'][0]['evidence_status'] = 'VERIFIED'
    write_json(bad, package)
    with pytest.raises(ValueError, match='missing or unverified evidence'):
        import_response_draft(root, bad)
    package = build_response_drafting_package(root)
    reviewer = next(item for item in package['entries'] if item['comment_id'] == 'R1-C01')
    reviewer['highlight'] = 'BRIGHT_GREEN'
    write_json(bad, package)
    with pytest.raises(ValueError, match='highlight'):
        import_response_draft(root, bad)
