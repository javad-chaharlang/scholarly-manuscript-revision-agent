from pathlib import Path

import pytest

from phase5_helpers import make_phase5_project
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.workflows.revision_execution_workflow import (
    import_completed_revision_drafts,
    prepare_revision_drafts,
)


def test_preparation_is_blank_deterministic_context(tmp_path: Path) -> None:
    root = make_phase5_project(tmp_path, action_count=2)
    result = prepare_revision_drafts(root)
    payload = read_json(result.draft_template_path)
    drafting_input = read_json(result.drafting_input_path)
    assert result.draft_count == 2
    assert all(entry['draft']['proposed_text'] == '' for entry in payload['drafts'])
    assert drafting_input['scientific_revision_text_generated_by_deterministic_code'] is False
    assert drafting_input['actions'][0]['exact_reviewer_comments'][0]['exact_comment']


def test_import_rejects_unknown_action_comment_and_stale_hash(tmp_path: Path) -> None:
    root = make_phase5_project(tmp_path, action_count=1)
    prepare_revision_drafts(root)
    payload = read_json(root / 'working' / 'revision_draft_template.json')
    draft = payload['drafts'][0]['draft']
    draft['proposed_text'] = 'Anonymous completed text.'
    draft['draft_status'] = 'DRAFTED'

    bad = root / 'working' / 'bad.json'
    altered = read_json(root / 'working' / 'revision_draft_template.json')
    altered['drafts'][0]['draft'].update(
        proposed_text='Anonymous completed text.', draft_status='DRAFTED',
        action_id='ACT-9999',
    )
    write_json(bad, altered)
    with pytest.raises(ValueError, match='unknown action'):
        import_completed_revision_drafts(root, bad)

    payload['drafts'][0]['exact_reviewer_comments'][0]['exact_comment'] = 'Altered.'
    write_json(bad, payload)
    with pytest.raises(ValueError, match='altered'):
        import_completed_revision_drafts(root, bad)

    payload = read_json(root / 'working' / 'revision_draft_template.json')
    payload['drafts'][0]['draft'].update(
        proposed_text='Anonymous completed text.', draft_status='DRAFTED',
        original_text_hash='f' * 64,
    )
    write_json(bad, payload)
    with pytest.raises(ValueError, match='original-text hash'):
        import_completed_revision_drafts(root, bad)
