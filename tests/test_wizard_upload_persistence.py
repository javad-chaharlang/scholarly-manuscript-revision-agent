from __future__ import annotations

from pathlib import Path

import pytest

from scholarly_revision.services.wizard_upload_service import (
    MANUSCRIPT_ROLE, REVIEWER_ROLE, UploadRecord, WizardUploadError,
    create_draft_directory, find_recoverable_drafts, load_manifest,
    persist_upload, remove_upload, restore_manifest, validate_record,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
DOCX_MIME = (
    'application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document'
)

def _saved_records(tmp_path: Path):
    draft_id, draft = create_draft_directory(draft_root=tmp_path / 'drafts')
    reviewer = persist_upload(
        payload=(FIXTURES / 'synthetic_reviewer_comments.docx').read_bytes(),
        original_name='../Reviewer.docx', mime_type=DOCX_MIME,
        role=REVIEWER_ROLE, draft_directory=draft)
    manuscript = persist_upload(
        payload=(FIXTURES / 'synthetic_manuscript.docx').read_bytes(),
        original_name='Manuscript.docx', mime_type=DOCX_MIME,
        role=MANUSCRIPT_ROLE, draft_directory=draft)
    return draft_id, draft, reviewer, manuscript

def test_serializable_records_are_safe_valid_and_use_normalized_roles(
        tmp_path: Path) -> None:
    _, draft, reviewer, manuscript = _saved_records(tmp_path)
    required_fields = set(UploadRecord.__dataclass_fields__)
    assert set(reviewer) == required_fields
    assert reviewer['role'] == REVIEWER_ROLE
    assert manuscript['role'] == MANUSCRIPT_ROLE
    assert reviewer['original_name'] == '../Reviewer.docx'
    assert '..' not in reviewer['safe_name']
    assert reviewer['safe_name'].startswith('reviewer_file-Reviewer-')
    assert Path(reviewer['temporary_path']).parent == draft / 'uploads'
    assert validate_record(reviewer, expected_role=REVIEWER_ROLE)['ready']
    assert validate_record(manuscript, expected_role=MANUSCRIPT_ROLE)['ready']
    assert not any(hasattr(value, 'read') for value in reviewer.values())

def test_required_uploads_survive_continue_back_rerun_and_empty_widget(
        tmp_path: Path) -> None:
    draft_id, draft, reviewer, manuscript = _saved_records(tmp_path)
    state = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'new_project_reviewer_upload_record': reviewer,
        'new_project_manuscript_upload_record': manuscript,
        'new_project_reviewer_uploader_widget': None,
        'new_project_manuscript_uploader_widget': None,
        'wiz_project_name': 'Synthetic draft',
    }
    for step in (3, 4, 5, 4, 3):
        manifest_path = write_manifest(
            draft_id=draft_id, draft_directory=draft,
            form_metadata=state,
            uploads={REVIEWER_ROLE: reviewer, MANUSCRIPT_ROLE: manuscript},
            current_step=step)
        restored: dict = {}
        restore_manifest(load_manifest(manifest_path), restored,
                         role_record_keys={
                             REVIEWER_ROLE: 'new_project_reviewer_upload_record',
                             MANUSCRIPT_ROLE: 'new_project_manuscript_upload_record',
                         })
        assert restored['new_project_reviewer_upload_record'] == reviewer
        assert restored['new_project_manuscript_upload_record'] == manuscript
        assert restored['wizard_step'] == step
    assert validate_record(reviewer, expected_role=REVIEWER_ROLE)['ready']
    assert state['new_project_reviewer_uploader_widget'] is None

def test_missing_temporary_file_and_hash_mismatch_are_detected(
        tmp_path: Path) -> None:
    _, _, reviewer, manuscript = _saved_records(tmp_path)
    reviewer_path = Path(reviewer['temporary_path'])
    reviewer_path.unlink()
    missing = validate_record(reviewer, expected_role=REVIEWER_ROLE)
    assert not missing['ready']
    assert missing['message'] == (
        'The temporary upload is missing; please select the file again.')
    manuscript_path = Path(manuscript['temporary_path'])
    original_payload = manuscript_path.read_bytes()
    manuscript_path.write_bytes(original_payload + b'changed')
    changed = validate_record(manuscript, expected_role=MANUSCRIPT_ROLE)
    assert not changed['ready']
    assert changed['message'] == (
        'The uploaded file changed after validation and must be revalidated.')
    repaired = persist_upload(
        payload=original_payload, original_name=manuscript['original_name'],
        mime_type=DOCX_MIME, role=MANUSCRIPT_ROLE,
        draft_directory=manuscript_path.parents[1],
        existing_record=manuscript)
    assert validate_record(repaired, expected_role=MANUSCRIPT_ROLE)['ready']

def test_zero_byte_and_structurally_invalid_docx_are_rejected(
        tmp_path: Path) -> None:
    _, draft = create_draft_directory(draft_root=tmp_path / 'drafts')
    with pytest.raises(WizardUploadError, match='empty'):
        persist_upload(payload=b'', original_name='Reviewer.docx',
                       mime_type=DOCX_MIME, role=REVIEWER_ROLE,
                       draft_directory=draft)
    with pytest.raises(WizardUploadError, match='structurally valid DOCX'):
        persist_upload(payload=b'not a zip', original_name='Reviewer.docx',
                       mime_type=DOCX_MIME, role=REVIEWER_ROLE,
                       draft_directory=draft)
    assert list((draft / 'uploads').iterdir()) == []

def test_draft_storage_inside_repository_is_refused() -> None:
    with pytest.raises(ValueError, match='outside the Git repository'):
        create_draft_directory(draft_root=ROOT / '.wizard-test-forbidden')
    assert not (ROOT / '.wizard-test-forbidden').exists()

class _Upload:
    def __init__(self, name: str, payload: bytes):
        self.name = name
        self.type = DOCX_MIME
        self.payload = payload
        self.read_count = 0

    def getvalue(self) -> bytes:
        self.read_count += 1
        return self.payload

def test_replacement_retains_old_record_until_new_validation_succeeds(
        tmp_path: Path, monkeypatch) -> None:
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    draft_id, draft, reviewer, _ = _saved_records(tmp_path)
    old_path = Path(reviewer['temporary_path'])
    invalid = _Upload('invalid.docx', b'not a docx')
    state = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'new_project_reviewer_upload_record': reviewer,
        'new_project_reviewer_uploader_widget': invalid,
    }
    monkeypatch.setattr(wizard.st, 'session_state', state)
    spec = wizard.SPEC_BY_ROLE[REVIEWER_ROLE]
    wizard._handle_upload(spec)
    assert invalid.read_count == 1
    assert state[spec.record_key] == reviewer
    assert old_path.is_file()
    replacement = _Upload(
        'replacement.docx',
        (FIXTURES / 'synthetic_manuscript.docx').read_bytes())
    state[spec.widget_key] = replacement
    wizard._handle_upload(spec)
    assert replacement.read_count == 1
    assert state[spec.record_key]['sha256'] != reviewer['sha256']
    assert not old_path.exists()
    assert Path(state[spec.record_key]['temporary_path']).is_file()

def test_remove_deletes_only_selected_upload(
        tmp_path: Path, monkeypatch) -> None:
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    draft_id, draft, reviewer, manuscript = _saved_records(tmp_path)
    state = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'new_project_reviewer_upload_record': reviewer,
        'new_project_manuscript_upload_record': manuscript,
    }
    monkeypatch.setattr(wizard.st, 'session_state', state)
    wizard._remove_saved_upload(wizard.SPEC_BY_ROLE[REVIEWER_ROLE])
    assert 'new_project_reviewer_upload_record' not in state
    assert not Path(reviewer['temporary_path']).exists()
    assert state['new_project_manuscript_upload_record'] == manuscript
    assert Path(manuscript['temporary_path']).is_file()
    assert state['new_project_wizard_events'][-1]['role'] == REVIEWER_ROLE

def test_browser_restart_recovers_manifest_and_valid_saved_files(
        tmp_path: Path) -> None:
    draft_id, draft, reviewer, manuscript = _saved_records(tmp_path)
    write_manifest(
        draft_id=draft_id, draft_directory=draft,
        form_metadata={'wiz_project_name': 'Recover me',
                       'wiz_workspace': str(tmp_path / 'workspace')},
        uploads={REVIEWER_ROLE: reviewer, MANUSCRIPT_ROLE: manuscript},
        current_step=5,
        events=[{'action': 'navigate', 'at': '2026-08-01T00:00:00+00:00'}])
    candidates = find_recoverable_drafts(tmp_path / 'drafts')
    assert len(candidates) == 1
    restored: dict = {}
    restore_manifest(
        candidates[0], restored,
        role_record_keys={
            REVIEWER_ROLE: 'new_project_reviewer_upload_record',
            MANUSCRIPT_ROLE: 'new_project_manuscript_upload_record',
        })
    assert restored['wizard_step'] == 5
    assert restored['wiz_project_name'] == 'Recover me'
    assert validate_record(
        restored['new_project_reviewer_upload_record'],
        expected_role=REVIEWER_ROLE)['ready']
    assert validate_record(
        restored['new_project_manuscript_upload_record'],
        expected_role=MANUSCRIPT_ROLE)['ready']

def test_step5_request_uses_saved_paths_not_widget_values(
        tmp_path: Path, monkeypatch) -> None:
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    draft_id, draft, reviewer, manuscript = _saved_records(tmp_path)
    state = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'new_project_reviewer_upload_record': reviewer,
        'new_project_manuscript_upload_record': manuscript,
        'new_project_reviewer_uploader_widget': None,
        'new_project_manuscript_uploader_widget': None,
        'wiz_project_name': 'Saved paths', 'wiz_manuscript_id': 'SAVED-1',
        'wiz_title': 'Synthetic manuscript', 'wiz_journal': 'Synthetic Journal',
        'wiz_round': 1, 'wiz_reviewer_count': 2,
        'wiz_manuscript_language': 'English',
        'wiz_response_language': 'English',
        'wiz_citation_style': 'numeric', 'wiz_result_status': 'DRAFT',
    }
    monkeypatch.setattr(wizard.st, 'session_state', state)
    request = wizard._request(tmp_path / 'workspace')
    assert request.reviewer_file == Path(reviewer['temporary_path'])
    assert request.manuscript_file == Path(manuscript['temporary_path'])
    assert reviewer['role'] == REVIEWER_ROLE
    assert manuscript['role'] == MANUSCRIPT_ROLE

def test_failed_creation_retains_uploads_and_success_clears_draft(
        tmp_path: Path, monkeypatch) -> None:
    from scholarly_revision.services.orchestrator_service import OrchestratorService
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    draft_id, draft, reviewer, manuscript = _saved_records(tmp_path)
    state = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'new_project_reviewer_upload_record': reviewer,
        'new_project_manuscript_upload_record': manuscript,
        'wiz_project_name': 'Creation lifecycle',
        'wiz_manuscript_id': 'CREATE-1', 'wiz_title': '',
        'wiz_journal': 'Synthetic Journal', 'wiz_round': 1,
        'wiz_reviewer_count': 2, 'wiz_manuscript_language': 'English',
        'wiz_response_language': 'English',
        'wiz_citation_style': 'numeric', 'wiz_result_status': 'DRAFT',
    }
    monkeypatch.setattr(wizard.st, 'session_state', state)
    workspace = tmp_path / 'workspace'
    service = OrchestratorService(workspace)
    with pytest.raises(ValueError, match='manuscript title'):
        service.validate_new_project(wizard._request(workspace))
    assert state['new_project_reviewer_upload_record'] == reviewer
    assert state['new_project_manuscript_upload_record'] == manuscript
    assert Path(reviewer['temporary_path']).is_file()
    assert draft.is_dir()

    state['wiz_title'] = 'Synthetic manuscript'
    project_state = service.create_project(
        wizard._request(workspace), actor='Synthetic Author')
    entry = service.registry.get(project_state.project_id)
    wizard._verify_project_input_hashes(entry.project_root)
    reviewer_copy = Path(entry.project_root) / 'input' / reviewer['safe_name']
    manuscript_copy = Path(entry.project_root) / 'input' / manuscript['safe_name']
    assert reviewer_copy.is_file() and manuscript_copy.is_file()
    assert reviewer_copy.read_bytes() == Path(reviewer['temporary_path']).read_bytes()
    assert manuscript_copy.read_bytes() == Path(manuscript['temporary_path']).read_bytes()
    wizard._clear_successful_draft()
    assert not draft.exists()
    assert 'new_project_reviewer_upload_record' not in state
    assert 'new_project_manuscript_upload_record' not in state

def _render_saved_card(record: dict) -> None:
    import streamlit as st
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    st.session_state['new_project_reviewer_upload_record'] = record
    wizard._render_upload(wizard.SPEC_BY_ROLE[wizard.REVIEWER_ROLE])

def test_saved_file_card_is_shown_when_native_uploader_is_empty(
        tmp_path: Path) -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    _, _, reviewer, _ = _saved_records(tmp_path)
    app = testing.AppTest.from_function(
        _render_saved_card, args=(reviewer,), default_timeout=30).run(timeout=30)
    assert not app.exception
    assert any('Reviewer comments DOCX' in item.value for item in app.markdown)
    assert any('Filename: ../Reviewer.docx' in item.value for item in app.markdown)
    assert {'Replace file', 'Remove file'} <= {item.label for item in app.button}
    assert app.file_uploader[0].value is None

def _render_complete_wizard() -> None:
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    wizard.render(actor='Synthetic Author')

def _button(app, label: str):
    return next(item for item in app.button if item.label == label)

def test_apptest_complete_back_continue_and_project_creation_scenario(
        tmp_path: Path) -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    app = testing.AppTest.from_function(
        _render_complete_wizard, default_timeout=60)
    app.session_state['new_project_recovery_dismissed'] = True
    app.run(timeout=60)
    fields = {item.label: item for item in app.text_input}
    fields['Project name'].set_value('AppTest persistent uploads')
    fields['Manuscript ID'].set_value('APPTEST-UPLOADS')
    fields['Manuscript title'].set_value('Anonymous synthetic manuscript')
    fields['Journal'].set_value('Synthetic Journal')
    app.run(timeout=60)
    _button(app, 'Continue').click().run(timeout=60)

    assert app.session_state['wizard_step'] == 2
    _button(app, 'Continue').click().run(timeout=60)
    assert app.session_state['wizard_step'] == 3
    app.file_uploader[0].upload(
        'Reviewer.docx',
        (FIXTURES / 'synthetic_reviewer_comments.docx').read_bytes(),
        DOCX_MIME)
    app.file_uploader[1].upload(
        'Manuscript.docx',
        (FIXTURES / 'synthetic_manuscript.docx').read_bytes(),
        DOCX_MIME)
    app.run(timeout=60)
    reviewer = dict(
        app.session_state['new_project_reviewer_upload_record'])
    manuscript = dict(
        app.session_state['new_project_manuscript_upload_record'])
    assert validate_record(reviewer, expected_role=REVIEWER_ROLE)['ready']
    assert validate_record(manuscript, expected_role=MANUSCRIPT_ROLE)['ready']
    assert {'Replace file', 'Remove file'} <= {
        item.label for item in app.button}

    _button(app, 'Continue').click().run(timeout=60)
    assert app.session_state['wizard_step'] == 4
    assert app.session_state['new_project_reviewer_upload_record'] == reviewer
    assert app.session_state['new_project_manuscript_upload_record'] == manuscript
    _button(app, 'Back').click().run(timeout=60)
    assert app.session_state['wizard_step'] == 3
    assert all(item.value is None for item in app.file_uploader)
    assert sum('Ready' in item.value for item in app.markdown) >= 2

    _button(app, 'Continue').click().run(timeout=60)
    _button(app, 'Continue').click().run(timeout=60)
    assert app.session_state['wizard_step'] == 5
    validation = app.dataframe[0].value
    assert validation['Ready'].tolist() == [True, True]
    workspace = tmp_path / 'manual-workspace'
    app.text_input[0].set_value(str(workspace))
    app.checkbox[0].set_value(True)
    app.run(timeout=60)
    assert not _button(app, 'Validate and create project').disabled
    _button(app, 'Validate and create project').click().run(timeout=120)
    assert not app.exception
    assert app.session_state['wizard_complete'] is True
    project_root = Path(app.session_state['project_root'])
    reviewer_copy = project_root / 'input' / reviewer['safe_name']
    manuscript_copy = project_root / 'input' / manuscript['safe_name']
    assert reviewer_copy.is_file() and manuscript_copy.is_file()
    assert reviewer_copy.read_bytes() == (
        FIXTURES / 'synthetic_reviewer_comments.docx').read_bytes()
    assert manuscript_copy.read_bytes() == (
        FIXTURES / 'synthetic_manuscript.docx').read_bytes()
    assert 'new_project_reviewer_upload_record' not in app.session_state
    assert 'new_project_manuscript_upload_record' not in app.session_state
