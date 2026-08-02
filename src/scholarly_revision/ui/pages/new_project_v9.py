from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from scholarly_revision.models.enums import ResultStatus
from scholarly_revision.services.orchestrator_service import NewProjectRequest, OrchestratorService
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.services.wizard_upload_service import (
    MANUSCRIPT_ROLE, REVIEWER_ROLE, WizardUploadError, clear_draft,
    create_draft_directory, find_recoverable_drafts, persist_upload,
    remove_upload, restore_manifest, utc_now, validate_record, write_manifest,
)
from scholarly_revision.ui.components.studio import banner, page_header
from scholarly_revision.ui.state import set_active_project

STEPS = ('Project identity', 'Languages and standards', 'Required inputs',
         'Optional inputs', 'Validation and confirmation')

@dataclass(frozen=True, slots=True)
class UploadSpec:
    role: str
    label: str
    extensions: tuple[str, ...]
    widget_key: str
    record_key: str
    required: bool = False

UPLOAD_SPECS = (
    UploadSpec(REVIEWER_ROLE, 'Reviewer comments DOCX', ('docx',),
               'new_project_reviewer_uploader_widget',
               'new_project_reviewer_upload_record', True),
    UploadSpec(MANUSCRIPT_ROLE, 'Manuscript DOCX', ('docx',),
               'new_project_manuscript_uploader_widget',
               'new_project_manuscript_upload_record', True),
    UploadSpec('editor_letter', 'Editor letter', ('docx',),
               'new_project_editor_letter_uploader_widget',
               'new_project_editor_letter_upload_record'),
    UploadSpec('result_registry', 'Results registry', ('json',),
               'new_project_result_registry_uploader_widget',
               'new_project_result_registry_upload_record'),
    UploadSpec('reference_registry', 'Reference registry', ('json',),
               'new_project_reference_registry_uploader_widget',
               'new_project_reference_registry_upload_record'),
    UploadSpec('response_sample', 'Response sample', ('docx',),
               'new_project_response_sample_uploader_widget',
               'new_project_response_sample_upload_record'),
    UploadSpec('previous_manuscript', 'Previous manuscript', ('docx',),
               'new_project_previous_manuscript_uploader_widget',
               'new_project_previous_manuscript_upload_record'),
    UploadSpec('journal_template', 'Journal template', ('docx',),
               'new_project_journal_template_uploader_widget',
               'new_project_journal_template_upload_record'),
)
SPEC_BY_ROLE = {spec.role: spec for spec in UPLOAD_SPECS}
ROLE_RECORD_KEYS = {spec.role: spec.record_key for spec in UPLOAD_SPECS}
WIZARD_FORM_KEYS = (
    'wiz_project_name', 'wiz_manuscript_id', 'wiz_title', 'wiz_journal',
    'wiz_round', 'wiz_reviewer_count', 'wiz_manuscript_language',
    'wiz_response_language', 'wiz_citation_style', 'wiz_result_status',
    'wiz_workspace',
)

def _ensure_draft() -> tuple[str, Path]:
    draft_id = st.session_state.get('new_project_draft_id')
    value = st.session_state.get('new_project_draft_directory')
    if draft_id and value:
        directory = Path(value).expanduser().resolve()
        if directory.name == draft_id:
            (directory / 'uploads').mkdir(parents=True, exist_ok=True)
            return str(draft_id), directory
    draft_id, directory = create_draft_directory()
    st.session_state['new_project_draft_id'] = draft_id
    st.session_state['new_project_draft_directory'] = str(directory)
    st.session_state.setdefault('new_project_wizard_events', [])
    return draft_id, directory

def _upload_records() -> dict[str, Mapping[str, Any]]:
    return {spec.role: st.session_state[spec.record_key] for spec in UPLOAD_SPECS
            if isinstance(st.session_state.get(spec.record_key), dict)}

def _record_event(action: str, role: str | None = None) -> None:
    events = list(st.session_state.get('new_project_wizard_events', []))
    event: dict[str, Any] = {'action': action, 'at': utc_now()}
    if role is not None:
        event['role'] = role
    events.append(event)
    st.session_state['new_project_wizard_events'] = events[-100:]

def _persist_manifest() -> None:
    draft_id, directory = _ensure_draft()
    write_manifest(
        draft_id=draft_id, draft_directory=directory,
        form_metadata=st.session_state, uploads=_upload_records(),
        current_step=int(st.session_state.get('wizard_step', 1)),
        events=list(st.session_state.get('new_project_wizard_events', [])),
    )

def _navigate(target_step: int) -> None:
    st.session_state['wizard_step'] = max(1, min(len(STEPS), target_step))
    _record_event('navigate')
    _persist_manifest()

def _nav(step: int) -> None:
    with st.container(horizontal=True, horizontal_alignment='right'):
        st.button('Back', icon=':material/arrow_back:', disabled=step == 1,
                  key=f'wizard_back_{step}', on_click=_navigate, args=(step - 1,))
        st.button('Continue', type='primary', icon=':material/arrow_forward:',
                  disabled=step == len(STEPS), key=f'wizard_next_{step}',
                  on_click=_navigate, args=(step + 1,))

def _handle_upload(spec: UploadSpec) -> None:
    upload = st.session_state.get(spec.widget_key)
    if upload is None:
        return
    # UploadedFile is transient. Read it once and immediately stop relying on it.
    payload = upload.getvalue()
    _, directory = _ensure_draft()
    previous = st.session_state.get(spec.record_key)
    try:
        record = persist_upload(
            payload=payload, original_name=str(upload.name),
            mime_type=getattr(upload, 'type', None), role=spec.role,
            draft_directory=directory,
            existing_record=previous if isinstance(previous, dict) else None,
        )
    except (WizardUploadError, OSError, ValueError) as exc:
        st.session_state[f'{spec.record_key}_error'] = str(exc)
        _record_event('upload_rejected', spec.role)
        _persist_manifest()
        return
    st.session_state[spec.record_key] = record
    st.session_state.pop(f'{spec.record_key}_error', None)
    st.session_state[f'{spec.record_key}_replace_mode'] = False
    if (isinstance(previous, dict)
            and previous.get('temporary_path') != record['temporary_path']):
        remove_upload(previous, draft_directory=directory)
    _record_event('upload_saved', spec.role)
    _persist_manifest()

def _begin_replace(spec: UploadSpec) -> None:
    st.session_state[f'{spec.record_key}_replace_mode'] = True
    st.session_state.pop(f'{spec.record_key}_error', None)

def _remove_saved_upload(spec: UploadSpec) -> None:
    _, directory = _ensure_draft()
    record = st.session_state.get(spec.record_key)
    if isinstance(record, dict):
        remove_upload(record, draft_directory=directory)
    st.session_state.pop(spec.record_key, None)
    st.session_state.pop(f'{spec.record_key}_error', None)
    st.session_state[f'{spec.record_key}_replace_mode'] = False
    try:
        st.session_state.pop(spec.widget_key, None)
    except Exception:
        pass
    _record_event('upload_removed', spec.role)
    _persist_manifest()

def _format_size(size: int) -> str:
    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    return f'{size / (1024 * 1024):.1f} MB'

def _saved_record_ready(spec: UploadSpec, record: Mapping[str, Any]) -> bool:
    if spec.required:
        return bool(validate_record(record, expected_role=spec.role)['ready'])
    try:
        path = Path(str(record['temporary_path']))
        return (path.is_file() and path.stat().st_size > 0
                and sha256_file(path) == record['sha256'])
    except (KeyError, OSError, TypeError, ValueError):
        return False

def _saved_file_card(spec: UploadSpec, record: Mapping[str, Any]) -> None:
    ready = _saved_record_ready(spec, record)
    filename = record.get('original_name', 'Unknown')
    role = record.get('role', spec.role)
    size = _format_size(int(record.get('size_bytes', 0)))
    digest = str(record.get('sha256', ''))[:12]
    uploaded = record.get('uploaded_at', 'Unknown')
    with st.container(border=True):
        with st.container(horizontal=True, horizontal_alignment='distribute'):
            st.markdown(f'**{spec.label}**')
            st.badge('Ready' if ready else 'Needs attention',
                     color='green' if ready else 'red',
                     icon=':material/check_circle:' if ready else ':material/error:')
        st.write(f'Filename: {filename}')
        st.caption(f'Role: {role} | Size: {size} | SHA-256: {digest} | Uploaded: {uploaded}')
        st.caption(str(record.get(
            'validation_message', 'Upload validation was not recorded.')))
        with st.container(horizontal=True):
            st.button('Replace file', icon=':material/upload_file:',
                      key=f'replace_{spec.role}', on_click=_begin_replace,
                      args=(spec,))
            st.button('Remove file', icon=':material/delete:',
                      key=f'remove_{spec.role}', on_click=_remove_saved_upload,
                      args=(spec,))

def _render_upload(spec: UploadSpec) -> None:
    record = st.session_state.get(spec.record_key)
    replace_mode = bool(st.session_state.get(f'{spec.record_key}_replace_mode'))
    suffix = 'Required' if spec.required else 'Optional'
    st.file_uploader(
        f'{spec.label} - {suffix}', type=list(spec.extensions),
        key=spec.widget_key, on_change=_handle_upload, args=(spec,),
        disabled=isinstance(record, dict) and not replace_mode,
    )
    error = st.session_state.get(f'{spec.record_key}_error')
    if error:
        st.error(error, icon=':material/error:')
        if isinstance(record, dict):
            st.info('The previously saved valid file was retained.',
                    icon=':material/verified:')
    if isinstance(record, dict):
        _saved_file_card(spec, record)
        if replace_mode:
            st.info(
                'Select a replacement above. The saved file remains active until the new file passes validation.',
                icon=':material/swap_horiz:',
            )

def _required_validation() -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    all_ready = True
    for role in (REVIEWER_ROLE, MANUSCRIPT_ROLE):
        spec = SPEC_BY_ROLE[role]
        check = validate_record(st.session_state.get(spec.record_key),
                                expected_role=role)
        rows.append({
            'Role': role,
            'File name': check['file_name'] or 'Not saved',
            'Size': check['size_bytes'],
            'Non-empty': check['non_empty'],
            'DOCX structure valid': check['valid_docx'],
            'SHA-256': check['sha256'],
            'Temporary file exists': check['temporary_file_exists'],
            'Ready': check['ready'],
        })
        all_ready = all_ready and bool(check['ready'])
    return rows, all_ready

def _record_path(role: str, *, required: bool = False) -> Path | None:
    spec = SPEC_BY_ROLE[role]
    record = st.session_state.get(spec.record_key)
    if not isinstance(record, dict):
        if required:
            message = ('Reviewer comments DOCX has not been saved.'
                       if role == REVIEWER_ROLE
                       else 'Manuscript DOCX has not been saved.')
            raise WizardUploadError(message)
        return None
    if required:
        check = validate_record(record, expected_role=role)
        if not check['ready']:
            raise WizardUploadError(str(check['message']))
    return Path(str(record['temporary_path']))

def _request(workspace: Path) -> NewProjectRequest:
    return NewProjectRequest(
        workspace_root=workspace,
        project_name=st.session_state.get('wiz_project_name', ''),
        manuscript_id=st.session_state.get('wiz_manuscript_id', ''),
        manuscript_title=st.session_state.get('wiz_title', ''),
        journal=st.session_state.get('wiz_journal', ''),
        revision_round=int(st.session_state.get('wiz_round', 1)),
        reviewer_count=int(st.session_state.get('wiz_reviewer_count', 2)),
        manuscript_language=st.session_state.get('wiz_manuscript_language', 'English'),
        response_language=st.session_state.get('wiz_response_language', 'English'),
        citation_style=st.session_state.get('wiz_citation_style', 'journal-required'),
        result_status=st.session_state.get('wiz_result_status', 'DRAFT'),
        reviewer_file=_record_path(REVIEWER_ROLE, required=True),
        manuscript_file=_record_path(MANUSCRIPT_ROLE, required=True),
        editor_letter=_record_path('editor_letter'),
        result_registry=_record_path('result_registry'),
        reference_registry=_record_path('reference_registry'),
        response_sample=_record_path('response_sample'),
        previous_manuscript=_record_path('previous_manuscript'),
        journal_template=_record_path('journal_template'),
    )

def _verify_project_input_hashes(project_root: str | Path) -> None:
    input_directory = Path(project_root).resolve() / 'input'
    for spec in UPLOAD_SPECS:
        record = st.session_state.get(spec.record_key)
        if not isinstance(record, dict):
            continue
        copied = input_directory / str(record['safe_name'])
        if not copied.is_file() or sha256_file(copied) != record['sha256']:
            raise OSError(f'Copied input hash verification failed for {spec.role}.')

def _friendly_creation_error(exc: Exception) -> str:
    if isinstance(exc, WizardUploadError):
        return str(exc)
    message = str(exc)
    if 'must not be blank' in message:
        return message[:1].upper() + message[1:] + '.'
    if isinstance(exc, FileExistsError):
        return 'A project with this name already exists in the selected workspace.'
    if 'workspace root must be outside' in message:
        return 'Choose a confidential workspace outside the Git repository.'
    return ('Project creation failed. Your wizard fields and saved uploads were '
            'retained so you can correct the issue and retry.')

def _clear_successful_draft() -> None:
    draft_id = str(st.session_state.get('new_project_draft_id', ''))
    directory = st.session_state.get('new_project_draft_directory')
    if draft_id and directory:
        clear_draft(draft_id=draft_id, draft_directory=directory)
    keys = {
        'new_project_draft_id', 'new_project_draft_directory',
        'new_project_wizard_events', 'new_project_recovery_candidates',
        'new_project_recovery_dismissed', 'wizard_step', 'wiz_privacy_confirm',
    }
    keys.update(WIZARD_FORM_KEYS)
    for spec in UPLOAD_SPECS:
        keys.update({spec.widget_key, spec.record_key,
                     f'{spec.record_key}_error',
                     f'{spec.record_key}_replace_mode'})
    for key in keys:
        st.session_state.pop(key, None)

def _restore_latest_draft() -> None:
    candidates = st.session_state.get('new_project_recovery_candidates', [])
    if candidates:
        restore_manifest(candidates[0], st.session_state,
                         role_record_keys=ROLE_RECORD_KEYS)
        st.session_state.pop('new_project_recovery_candidates', None)
        _record_event('draft_resumed')
        _persist_manifest()

def _start_new_draft() -> None:
    st.session_state['new_project_recovery_dismissed'] = True
    st.session_state.pop('new_project_recovery_candidates', None)
    _ensure_draft()
    _record_event('draft_started')
    _persist_manifest()

def _offer_recovery() -> bool:
    if st.session_state.get('new_project_draft_id'):
        return False
    if not st.session_state.get('new_project_recovery_dismissed'):
        candidates = st.session_state.get('new_project_recovery_candidates')
        if candidates is None:
            candidates = find_recoverable_drafts()
            st.session_state['new_project_recovery_candidates'] = candidates
        if candidates:
            latest = candidates[0]
            modified = latest.get('modified_at', 'at an unknown time')
            saved_step = latest.get('current_step', 1)
            with st.container(border=True):
                st.subheader('Resume unfinished project draft', anchor=False)
                st.caption(f'Saved {modified} | Step {saved_step} of {len(STEPS)}')
                with st.container(horizontal=True):
                    st.button('Resume saved draft', type='primary',
                              icon=':material/restore:',
                              on_click=_restore_latest_draft)
                    st.button('Start new draft', icon=':material/note_add:',
                              on_click=_start_new_draft)
            return True
    _ensure_draft()
    return False

def _text_field(label: str, data_key: str, widget_key: str) -> None:
    st.session_state[data_key] = st.text_input(
        label, value=str(st.session_state.get(data_key, '')), key=widget_key)

def _select_field(label: str, options: list[str], data_key: str,
                  widget_key: str, *, default: str) -> None:
    current = str(st.session_state.get(data_key, default))
    index = options.index(current) if current in options else options.index(default)
    st.session_state[data_key] = st.selectbox(
        label, options, index=index, key=widget_key)

def _render_confirmation(actor: str | None) -> None:
    workspace_text = st.text_input(
        'Workspace location - outside Git',
        value=str(st.session_state.get('wiz_workspace')
                  or st.session_state.get('workspace_root', '')),
        key='new_project_workspace_widget')
    st.session_state['wiz_workspace'] = workspace_text
    rows, uploads_ready = _required_validation()
    st.dataframe(rows, hide_index=True)
    for role in (REVIEWER_ROLE, MANUSCRIPT_ROLE):
        check = validate_record(
            st.session_state.get(SPEC_BY_ROLE[role].record_key),
            expected_role=role)
        if not check['ready']:
            st.error(check['message'], icon=':material/error:')
    if not uploads_ready:
        st.warning(
            'Return to Step 3 and upload a non-empty valid DOCX file.',
            icon=':material/upload_file:')
    st.info(
        'Files remain local. The workspace registry stores safe metadata only.',
        icon=':material/lock:')
    confirmed = st.checkbox(
        'I confirm this workspace is local, confidential, and outside the repository.',
        key='wiz_privacy_confirm')
    create_clicked = st.button(
        'Validate and create project', type='primary',
        icon=':material/check_circle:',
        disabled=not (confirmed and uploads_ready), key='wizard_create')
    if not create_clicked:
        return
    try:
        # Recheck bytes, hash, readability, and DOCX structure immediately.
        _, still_ready = _required_validation()
        if not still_ready:
            raise WizardUploadError(
                'A required saved upload is no longer valid. Return to Step 3 and select it again.')
        workspace = Path(workspace_text).expanduser().resolve()
        service = OrchestratorService(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        with st.status(
            'Validating saved DOCX files and creating the project...',
            expanded=True,
        ):
            request = _request(workspace)
            service.validate_new_project(request)
            state = service.create_project(
                request, actor=actor or 'local-author')
            entry = service.registry.get(state.project_id)
            _verify_project_input_hashes(entry.project_root)
        st.session_state['workspace_root'] = str(workspace)
        set_active_project(
            st.session_state, project_id=entry.project_id,
            project_root=entry.project_root)
        _clear_successful_draft()
        st.session_state['wizard_complete'] = True
        st.rerun()
    except Exception as exc:
        st.error(_friendly_creation_error(exc), icon=':material/error:')

def render(orchestrator=None, project_root=None, actor=None) -> None:
    page_header(
        'New Project',
        'Five-step validation wizard for a confidential local revision workspace.',
        icon=':material/create_new_folder:',
    )
    if st.session_state.get('wizard_complete'):
        banner('success',
               'Project created and registered. It can be resumed after any app restart.')
        if st.button('Create another project', icon=':material/add:'):
            st.session_state['wizard_complete'] = False
            st.session_state['wizard_step'] = 1
            st.rerun()
        return
    if _offer_recovery():
        return
    step = max(1, min(len(STEPS),
                      int(st.session_state.get('wizard_step', 1))))
    st.session_state['wizard_step'] = step
    st.progress(step / len(STEPS),
                text=f'Step {step} of {len(STEPS)} - {STEPS[step - 1]}')
    with st.container(border=True):
        if step == 1:
            _text_field('Project name', 'wiz_project_name',
                        'new_project_project_name_widget')
            _text_field('Manuscript ID', 'wiz_manuscript_id',
                        'new_project_manuscript_id_widget')
            _text_field('Manuscript title', 'wiz_title',
                        'new_project_title_widget')
            _text_field('Journal', 'wiz_journal',
                        'new_project_journal_widget')
            st.session_state['wiz_round'] = st.number_input(
                'Revision round', min_value=1,
                value=int(st.session_state.get('wiz_round', 1)),
                key='new_project_revision_round_widget')
        elif step == 2:
            _select_field(
                'Manuscript language', ['English', 'Persian', 'Other'],
                'wiz_manuscript_language',
                'new_project_manuscript_language_widget', default='English')
            _select_field(
                'Response language', ['English', 'Persian', 'Other'],
                'wiz_response_language',
                'new_project_response_language_widget', default='English')
            st.session_state['wiz_citation_style'] = st.text_input(
                'Citation style',
                value=str(st.session_state.get(
                    'wiz_citation_style', 'journal-required')),
                key='new_project_citation_style_widget')
            _select_field(
                'Result status', [item.value for item in ResultStatus],
                'wiz_result_status', 'new_project_result_status_widget',
                default='DRAFT')
            st.session_state['wiz_reviewer_count'] = st.number_input(
                'Reviewer count', min_value=1,
                value=int(st.session_state.get('wiz_reviewer_count', 2)),
                key='new_project_reviewer_count_widget')
        elif step == 3:
            _render_upload(SPEC_BY_ROLE[REVIEWER_ROLE])
            _render_upload(SPEC_BY_ROLE[MANUSCRIPT_ROLE])
            st.caption(
                'Zero-byte, empty, unreadable, or structurally invalid DOCX files are rejected.')
        elif step == 4:
            for spec in UPLOAD_SPECS:
                if not spec.required:
                    _render_upload(spec)
        else:
            _render_confirmation(actor)
    _persist_manifest()
    _nav(step)
