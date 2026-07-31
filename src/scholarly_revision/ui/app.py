'''Production local Streamlit entry point for Phase 8.'''

from __future__ import annotations

import importlib
from pathlib import Path

import streamlit as st

from scholarly_revision.services.orchestrator_service import OrchestratorService
from scholarly_revision.ui.components import render_project_selector
from scholarly_revision.ui.state import initialize_session, redact_exception


PAGES = {
    'Dashboard': 'dashboard',
    'New Project': 'new_project',
    'Input Files': 'input_files',
    'Reviewer Comments': 'reviewer_comments',
    'Gap Analysis': 'gap_analysis',
    'Revision Plan': 'revision_plan',
    'Text Approval': 'text_approval',
    'Manuscript Versions': 'manuscript_versions',
    'Reference Audit': 'reference_audit',
    'Scientific QA': 'scientific_qa',
    'Response Letter': 'response_letter',
    'Visual QA': 'visual_qa',
    'Final Release': 'final_release',
    'Settings': 'settings',
}


def _page(name: str):
    return importlib.import_module(
        f'scholarly_revision.ui.pages.{PAGES[name]}'
    )


def main() -> None:
    st.set_page_config(
        page_title='Scholarly Manuscript Revision',
        page_icon='SMR',
        layout='wide',
        initial_sidebar_state='expanded',
    )
    initialize_session(st.session_state)
    st.sidebar.title('Scholarly Revision')
    st.sidebar.caption('Local deterministic workflow')
    workspace = st.sidebar.text_input(
        'Workspace root',
        value=st.session_state.get('workspace_root', ''),
        help='Choose a local directory outside the Git repository.',
    )
    st.session_state['workspace_root'] = workspace
    actor = st.sidebar.text_input(
        'Decision maker',
        value=st.session_state.get('actor', ''),
        help='Recorded with explicit human decisions.',
    )
    st.session_state['actor'] = actor
    selected_page = st.sidebar.radio('Page', list(PAGES), key='page_navigation')

    if selected_page == 'New Project':
        _page(selected_page).render(actor=actor)
        return
    if not workspace.strip():
        st.title('Scholarly Manuscript Revision')
        st.warning('Choose an external workspace root or open New Project.')
        return
    try:
        orchestrator = OrchestratorService(Path(workspace))
        selected = render_project_selector(orchestrator)
    except Exception as exc:
        st.error(redact_exception(exc))
        return
    if selected is None:
        if selected_page == 'Settings':
            _page(selected_page).render(orchestrator, None, actor)
        else:
            st.title(selected_page)
            st.info('Create a project before opening this page.')
        return
    _page(selected_page).render(orchestrator, selected.project_root, actor)


if __name__ == '__main__':
    main()
