from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from scholarly_revision.models.enums import ResultStatus
from scholarly_revision.services.orchestrator_service import NewProjectRequest, OrchestratorService
from scholarly_revision.tools.docx_reader import read_docx
from scholarly_revision.ui.components.studio import banner, page_header
from scholarly_revision.ui.state import redact_exception, save_uploaded_file, set_active_project

STEPS = ('Project identity', 'Languages and standards', 'Required inputs',
         'Optional inputs', 'Validation and confirmation')

def _nav(step: int) -> None:
    with st.container(horizontal=True, horizontal_alignment='right'):
        if st.button('Back', icon=':material/arrow_back:', disabled=step == 1, key=f'wizard_back_{step}'):
            st.session_state['wizard_step'] = step - 1; st.rerun()
        if st.button('Continue', type='primary', icon=':material/arrow_forward:',
                     disabled=step == 5, key=f'wizard_next_{step}'):
            st.session_state['wizard_step'] = step + 1; st.rerun()

def _upload(label: str, key: str, types: list[str], required: bool = False):
    suffix = 'Required' if required else 'Optional'
    return st.file_uploader(f'{label} · {suffix}', type=types, key=key)

def _file_rows() -> list[dict]:
    roles = [('Reviewer comments', 'wiz_reviewer'), ('Manuscript', 'wiz_manuscript'),
             ('Editor letter', 'wiz_editor'), ('Results registry', 'wiz_results'),
             ('Reference registry', 'wiz_references'), ('Response sample', 'wiz_response'),
             ('Previous manuscript', 'wiz_previous'), ('Journal template', 'wiz_template')]
    rows = []
    for role, key in roles:
        upload = st.session_state.get(key)
        if upload is not None:
            payload = upload.getvalue()
            rows.append({'Role': role, 'File': upload.name, 'Size': len(payload),
                         'SHA-256': sha256(payload).hexdigest() if payload else 'EMPTY'})
    return rows

def _materialize(upload, staging: Path, role: str, required: bool = False):
    if upload is None:
        if required: raise ValueError(f'{role} is required')
        return None
    return save_uploaded_file(upload, staging / role)

def _request(workspace: Path, staging: Path) -> NewProjectRequest:
    return NewProjectRequest(
        workspace_root=workspace, project_name=st.session_state.get('wiz_project_name', ''),
        manuscript_id=st.session_state.get('wiz_manuscript_id', ''),
        manuscript_title=st.session_state.get('wiz_title', ''),
        journal=st.session_state.get('wiz_journal', ''),
        revision_round=int(st.session_state.get('wiz_round', 1)),
        reviewer_count=int(st.session_state.get('wiz_reviewer_count', 2)),
        manuscript_language=st.session_state.get('wiz_manuscript_language', 'English'),
        response_language=st.session_state.get('wiz_response_language', 'English'),
        citation_style=st.session_state.get('wiz_citation_style', 'journal-required'),
        result_status=st.session_state.get('wiz_result_status', 'DRAFT'),
        reviewer_file=_materialize(st.session_state.get('wiz_reviewer'), staging, 'reviewer', True),
        manuscript_file=_materialize(st.session_state.get('wiz_manuscript'), staging, 'manuscript', True),
        editor_letter=_materialize(st.session_state.get('wiz_editor'), staging, 'editor'),
        result_registry=_materialize(st.session_state.get('wiz_results'), staging, 'results'),
        reference_registry=_materialize(st.session_state.get('wiz_references'), staging, 'references'),
        response_sample=_materialize(st.session_state.get('wiz_response'), staging, 'response'),
        previous_manuscript=_materialize(st.session_state.get('wiz_previous'), staging, 'previous'),
        journal_template=_materialize(st.session_state.get('wiz_template'), staging, 'template'))

def render(orchestrator=None, project_root=None, actor=None) -> None:
    page_header('New Project', 'Five-step validation wizard for a confidential local revision workspace.',
                icon=':material/create_new_folder:')
    if st.session_state.get('wizard_complete'):
        banner('success', 'Project created and registered. It can be resumed after any app restart.')
        if st.button('Create another project', icon=':material/add:'):
            st.session_state['wizard_complete'] = False; st.session_state['wizard_step'] = 1; st.rerun()
        return
    step = int(st.session_state.get('wizard_step', 1))
    st.progress(step / len(STEPS), text=f'Step {step} of {len(STEPS)} · {STEPS[step - 1]}')
    with st.container(border=True):
        if step == 1:
            st.text_input('Project name', key='wiz_project_name')
            st.text_input('Manuscript ID', key='wiz_manuscript_id')
            st.text_input('Manuscript title', key='wiz_title')
            st.text_input('Journal', key='wiz_journal')
            st.number_input('Revision round', min_value=1, value=1, key='wiz_round')
        elif step == 2:
            st.selectbox('Manuscript language', ['English', 'Persian', 'Other'], key='wiz_manuscript_language')
            st.selectbox('Response language', ['English', 'Persian', 'Other'], key='wiz_response_language')
            st.text_input('Citation style', value='journal-required', key='wiz_citation_style')
            st.selectbox('Result status', [item.value for item in ResultStatus], key='wiz_result_status')
            st.number_input('Reviewer count', min_value=1, value=2, key='wiz_reviewer_count')
        elif step == 3:
            _upload('Reviewer comments DOCX', 'wiz_reviewer', ['docx'], True)
            _upload('Manuscript DOCX', 'wiz_manuscript', ['docx'], True)
            st.caption('Zero-byte, empty, unreadable, or structurally invalid DOCX files are rejected.')
        elif step == 4:
            _upload('Editor letter', 'wiz_editor', ['docx'])
            _upload('Results registry', 'wiz_results', ['json'])
            _upload('Reference registry', 'wiz_references', ['json'])
            _upload('Response sample', 'wiz_response', ['docx'])
            _upload('Previous manuscript', 'wiz_previous', ['docx'])
            _upload('Journal template', 'wiz_template', ['docx'])
        else:
            workspace_text = st.text_input('Workspace location · outside Git',
                                           value=st.session_state.get('workspace_root', ''),
                                           key='wiz_workspace')
            rows = _file_rows()
            st.dataframe(rows, hide_index=True)
            st.info('Files remain local. The workspace registry stores safe metadata only.',
                    icon=':material/lock:')
            confirmed = st.checkbox('I confirm this workspace is local, confidential, and outside the repository.',
                                    key='wiz_privacy_confirm')
            if st.button('Validate and create project', type='primary', icon=':material/check_circle:',
                         disabled=not confirmed, key='wizard_create'):
                try:
                    workspace = Path(workspace_text).expanduser().resolve()
                    service = OrchestratorService(workspace)
                    workspace.mkdir(parents=True, exist_ok=True)
                    with st.status('Validating DOCX structure and creating the project...', expanded=True):
                        with TemporaryDirectory(dir=workspace) as staging_name:
                            request = _request(workspace, Path(staging_name))
                            service.validate_new_project(request)
                            state = service.create_project(request, actor=actor or 'local-author')
                    entry = service.registry.get(state.project_id)
                    st.session_state['workspace_root'] = str(workspace)
                    set_active_project(st.session_state, project_id=entry.project_id,
                                       project_root=entry.project_root)
                    st.session_state['wizard_complete'] = True
                    st.rerun()
                except Exception as exc:
                    st.error(redact_exception(exc), icon=':material/error:')
    _nav(step)
