'''Scholarly Revision Studio: Phase 9 Streamlit entry point.'''
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.orchestrator_service import OrchestratorService
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.ui.components import render_project_selector
from scholarly_revision.ui.i18n import is_rtl, t
from scholarly_revision.ui.layout_shell import (
    render_application_shell,
    render_sidebar_brand,
    render_sidebar_project_context,
    render_sidebar_system_controls,
)
from scholarly_revision.ui.navigation import PAGE_SPECS, page_available
from scholarly_revision.ui.pages.dashboard_v9 import APPLICATION_VERSION
from scholarly_revision.ui.state import initialize_session, redact_exception
from scholarly_revision.ui.theme import apply_theme


# Compatibility map retained for integrations that predate the System-level
# Agent Tasks workspace. Live navigation is built from PAGE_SPECS below.
PAGES = {
    spec.title: spec.module for spec in PAGE_SPECS if spec.key != 'agent_tasks'
}
V9_PAGE_KEYS = {
    'dashboard', 'new_project', 'input_files', 'reviewer_comments',
    'gap_analysis', 'revision_plan', 'text_approval', 'manuscript_versions',
    'reference_audit', 'scientific_qa', 'response_letter', 'visual_qa',
    'final_release', 'settings',
    'agent_tasks',
}


def _renderer(
    spec: Any, orchestrator: Any, selected: Any, actor: str,
    page_handles: dict[str, Any],
) -> Callable[[], None]:
    def page() -> None:
        module_name = f'{spec.module}_v9' if spec.key in V9_PAGE_KEYS else spec.module
        module = importlib.import_module(
            f'scholarly_revision.ui.pages.{module_name}'
        )
        if spec.project_required and selected is None:
            st.title(t(spec.key, st.session_state), anchor=False)
            st.info(
                t('getting_started_hint', st.session_state),
                icon=':material/folder_off:',
            )
            return
        project_root = selected.project_root if selected else None
        if spec.key == 'dashboard':
            module.render(
                orchestrator, project_root, actor,
                page_handles=page_handles,
            )
        else:
            module.render(orchestrator, project_root, actor)
    page.__name__ = f'page_{spec.key}'
    return page


def _context() -> tuple[Any | None, Any | None, str]:
    context_label = t('project_context', st.session_state)
    st.sidebar.markdown(f'### {context_label}')
    actor = st.sidebar.text_input(
        t('decision_maker', st.session_state),
        value=st.session_state.get('actor', ''),
        key='global_actor',
    )
    st.session_state['actor'] = actor
    workspace = st.sidebar.text_input(
        t('workspace_root', st.session_state),
        value=st.session_state.get('workspace_root', ''),
        help=t('getting_started_hint', st.session_state),
        key='global_workspace',
    )
    st.session_state['workspace_root'] = workspace
    if not workspace.strip():
        return None, None, actor
    try:
        service = OrchestratorService(Path(workspace))
        return service, render_project_selector(service), actor
    except Exception as exc:
        st.sidebar.error(redact_exception(exc))
        return None, None, actor


def main() -> None:
    st.set_page_config(
        page_title='Scholarly Revision Studio',
        page_icon=':material/science:',
        layout='wide',
        initial_sidebar_state='expanded',
    )
    initialize_session(st.session_state)
    render_sidebar_brand()
    apply_theme(rtl=is_rtl(st.session_state))
    orchestrator, selected, actor = _context()
    state: ProjectState | None = None
    if selected is not None:
        state = ProjectStateService(selected.project_root).load().state
    grouped: dict[str, list[Any]] = {}
    handles: dict[str, Any] = {}
    group_keys = {
        'Overview': 'overview',
        'Intake & Analysis': 'intake_analysis',
        'Revision': 'revision',
        'Quality Assurance': 'quality_assurance',
        'Release': 'release',
        'System': 'system',
    }
    for spec in PAGE_SPECS:
        if not page_available(
            spec.key, state, project_selected=selected is not None,
        ):
            continue
        page = st.Page(
            _renderer(spec, orchestrator, selected, actor, handles),
            title=t(spec.key, st.session_state),
            icon=spec.icon,
            url_path=spec.url_path,
            default=spec.key == 'dashboard',
        )
        handles[spec.key] = page
        group_label = t(group_keys[spec.group], st.session_state)
        grouped.setdefault(group_label, []).append(page)
    current = st.navigation(grouped, position='top', expanded=True)
    render_sidebar_project_context(selected, orchestrator)
    render_sidebar_system_controls(
        handles,
        active_page=current.title,
        application_version=APPLICATION_VERSION,
    )
    render_application_shell(selected, orchestrator, handles)
    current.run()


if __name__ == '__main__':
    main()
