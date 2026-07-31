from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from scholarly_revision.models.enums import ResultStatus
from scholarly_revision.services.orchestrator_service import (
    NewProjectRequest, OrchestratorService,
)
from scholarly_revision.ui.components import page_title
from scholarly_revision.ui.state import (
    redact_exception, save_uploaded_file, set_active_project,
)


def _materialize(upload, staging: Path, role: str, required: bool = False):
    if upload is None:
        if required:
            raise ValueError(f'{role} is required')
        return None
    return save_uploaded_file(upload, staging / role)


def render(orchestrator=None, project_root=None, actor=None) -> None:
    page_title('New Project', 'Create a confidential local project from validated DOCX inputs.')
    with st.form('new_project_form'):
        left, right = st.columns(2)
        project_name = left.text_input('Project name')
        manuscript_id = right.text_input('Manuscript ID')
        manuscript_title = left.text_input('Manuscript title')
        journal = right.text_input('Journal')
        revision_round = left.number_input('Revision round', min_value=1, value=1)
        reviewer_count = right.number_input('Reviewer count', min_value=1, value=2)
        manuscript_language = left.text_input('Manuscript language', value='English')
        response_language = right.text_input('Response language', value='English')
        citation_style = left.text_input('Citation style', value='journal-required')
        result_status = right.selectbox('Result status', [item.value for item in ResultStatus])
        workspace_root = st.text_input(
            'Workspace root (must be outside this Git repository)',
            value=st.session_state.get('workspace_root', ''),
        )
        reviewer_file = st.file_uploader('Reviewer file (DOCX)', type=['docx'])
        manuscript_file = st.file_uploader('Manuscript file (DOCX)', type=['docx'])
        editor_letter = st.file_uploader('Optional editor letter (DOCX)', type=['docx'])
        result_registry = st.file_uploader('Optional result registry (JSON)', type=['json'])
        reference_registry = st.file_uploader('Optional reference registry (JSON)', type=['json'])
        response_sample = st.file_uploader('Optional response sample (DOCX)', type=['docx'])
        submitted = st.form_submit_button('Validate and create project')
    if not submitted:
        return
    try:
        workspace = Path(workspace_root).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        service = OrchestratorService(workspace)
        with TemporaryDirectory(dir=workspace) as staging_name:
            staging = Path(staging_name)
            request = NewProjectRequest(
                workspace_root=workspace,
                project_name=project_name,
                manuscript_id=manuscript_id,
                manuscript_title=manuscript_title,
                journal=journal,
                revision_round=int(revision_round),
                reviewer_count=int(reviewer_count),
                manuscript_language=manuscript_language,
                response_language=response_language,
                citation_style=citation_style,
                result_status=result_status,
                reviewer_file=_materialize(reviewer_file, staging, 'reviewer', True),
                manuscript_file=_materialize(manuscript_file, staging, 'manuscript', True),
                editor_letter=_materialize(editor_letter, staging, 'editor'),
                result_registry=_materialize(result_registry, staging, 'results'),
                reference_registry=_materialize(reference_registry, staging, 'references'),
                response_sample=_materialize(response_sample, staging, 'response_sample'),
            )
            state = service.create_project(
                request, actor=(actor or st.session_state.get('actor') or 'local-author'),
            )
        entry = service.registry.get(state.project_id)
        st.session_state['workspace_root'] = str(workspace)
        set_active_project(
            st.session_state, project_id=entry.project_id,
            project_root=entry.project_root,
        )
        st.success(f'Project created in {entry.project_root}')
        st.info(f'Initial state: {state.state.value}')
    except Exception as exc:
        st.error(redact_exception(exc))
