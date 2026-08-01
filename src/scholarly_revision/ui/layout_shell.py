'''Professional shared shell for the local revision workspace.'''
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.ui.i18n import LANGUAGES, status_label, t
from scholarly_revision.ui.layout import abbreviate_path, state_progress, workflow_step_states
from scholarly_revision.ui.state import redact_exception

def _privacy_badges() -> None:
    with st.container(horizontal=True):
        st.badge(
            'Local storage',
            icon=':material/save:', color='green',
        )
        st.badge(
            'AI transmission requires approval',
            icon=':material/privacy_tip:', color='orange',
        )


def render_sidebar_brand() -> None:
    with st.sidebar:
        product = t('product', st.session_state)
        st.markdown(f'## :material/science: {product}')
        _privacy_badges()
        current_code = st.session_state.get('ui_language', 'en')
        current_name = next(
            (name for name, code in LANGUAGES.items() if code == current_code),
            'English',
        )
        selected = st.segmented_control(
            t('language', st.session_state),
            list(LANGUAGES), default=current_name,
            key='ui_language_selector',
        )
        st.session_state['ui_language'] = LANGUAGES.get(selected or current_name, 'en')


def render_sidebar_project_context(
    selected: Any | None, orchestrator: Any | None,
) -> None:
    with st.sidebar:
        if selected is None or orchestrator is None:
            st.info(
                t('privacy_notice', st.session_state),
                icon=':material/privacy_tip:',
            )
            st.caption(t('getting_started_hint', st.session_state))
            return
        root = Path(selected.project_root)
        record = ProjectStateService(root).load()
        data = orchestrator.dashboard(root)
        progress = state_progress(record.state, record.blocked_from)
        state_label = status_label(record.state, st.session_state)
        st.badge(
            state_label,
            color='red' if record.state.value == 'BLOCKED' else 'blue',
        )
        completion = t('completion', st.session_state)
        st.progress(progress, text=f'{completion} | {progress}%')
        next_label = t('next_action', st.session_state)
        next_value = data.get('next_recommended_action', record.next_required_action)
        st.caption(f'**{next_label}:** {next_value}')
        blocker_count = len(data.get('blockers') or [])
        st.metric(t('blockers', st.session_state), blocker_count, border=True)


def render_sidebar_system_controls(
    page_handles: Mapping[str, Any], *, active_page: str,
    application_version: str,
) -> None:
    with st.sidebar:
        controls = t('system_controls', st.session_state)
        st.markdown(f'### {controls}')
        settings = page_handles.get('settings')
        if settings is not None:
            st.page_link(
                settings, label=t('settings', st.session_state),
                icon=':material/settings:',
            )
        workspace = str(st.session_state.get('workspace_root', '')).strip()
        if st.button(
            t('open_workspace', st.session_state),
            icon=':material/folder_open:',
            disabled=not bool(workspace),
            key='open_workspace_folder',
        ):
            try:
                os.startfile(str(Path(workspace).resolve()))
            except (OSError, ValueError) as exc:
                st.error(redact_exception(exc))
        if st.button(
            t('refresh_project', st.session_state),
            icon=':material/refresh:',
            key='refresh_project',
        ):
            st.rerun()
        st.badge(
            t('saved_locally', st.session_state),
            icon=':material/save:', color='green',
        )
        active_label = t('active_page', st.session_state)
        st.caption(f'{active_label}: {active_page}')
        version_label = t('application_version', st.session_state)
        st.caption(f'{version_label}: {application_version}')


def render_welcome_context(page_handles: Mapping[str, Any]) -> None:
    with st.container(border=True, key='srs_welcome_hero'):
        _privacy_badges()
        product = t('product', st.session_state)
        st.markdown(f'# {product}')
        st.markdown(t('value_proposition', st.session_state))
        st.caption(t('welcome_hint', st.session_state))
        actions = (
            ('create_new_project', 'new_project', 'primary', ':material/add:'),
            ('open_existing_project', 'projects', 'secondary', ':material/folder_open:'),
            ('configure_workspace', 'settings', 'secondary', ':material/tune:'),
        )
        with st.container(horizontal=True, key='srs_hero_actions'):
            for label_key, page_key, button_type, icon in actions:
                page = page_handles.get(page_key)
                if st.button(
                    t(label_key, st.session_state),
                    icon=icon,
                    type=button_type,
                    disabled=page is None,
                    key=f'hero_{page_key}',
                ):
                    st.switch_page(page)


def render_project_context(project_root: str, orchestrator: Any) -> None:
    root = Path(project_root)
    manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
    record = ProjectStateService(root).load()
    data = orchestrator.dashboard(root)
    progress = state_progress(record.state, record.blocked_from)
    modified = datetime.fromtimestamp(root.stat().st_mtime).astimezone()
    with st.container(border=True, key='srs_context_bar'):
        with st.container(horizontal=True):
            _privacy_badges()
            readiness = str(data.get('release_readiness', 'NOT_EVALUATED'))
            st.badge(
                status_label(readiness, st.session_state),
                color='green' if readiness == 'READY' else 'orange',
            )
        st.markdown(f'## {manifest.manuscript_title}')
        manuscript_label = t('manuscript_id', st.session_state)
        journal_label = t('journal', st.session_state)
        round_label = t('revision_round', st.session_state)
        st.caption(
            f'{manuscript_label}: {manifest.manuscript_id} | '
            f'{journal_label}: {manifest.journal} | '
            f'{round_label}: {manifest.revision_round}'
        )
        state_label = status_label(record.state, st.session_state)
        workflow_label = t('current_state', st.session_state)
        st.progress(
            progress,
            text=f'{workflow_label}: {state_label} | {progress}%',
        )
        next_label = t('next_action', st.session_state)
        next_value = data.get('next_recommended_action', record.next_required_action)
        st.markdown(f'**{next_label}:** {next_value}')
        modified_label = t('last_modified', st.session_state)
        workspace_label = t('workspace_root', st.session_state)
        st.caption(
            f'{modified_label}: {modified:%Y-%m-%d %H:%M} | '
            f'{workspace_label}: {abbreviate_path(root)}'
        )


def render_workflow_stepper(
    record: Any | None, page_handles: Mapping[str, Any],
) -> None:
    st.subheader(t('workflow_overview', st.session_state), anchor=False)
    icons = {
        'complete': ':material/check_circle:',
        'active': ':material/radio_button_checked:',
        'pending': ':material/schedule:',
        'warning': ':material/warning:',
        'blocked': ':material/error:',
    }
    with st.container(
        border=True, key='srs_stepper', horizontal=True,
        vertical_alignment='center',
    ):
        for index, step in enumerate(workflow_step_states(record), 1):
            status = str(step['state'])
            page = page_handles.get(str(step['page']))
            step_label_key = str(step['label_key'])
            step_label = t(step_label_key, st.session_state)
            label = f'{index}. {step_label}'
            enabled = bool(step['enabled']) and page is not None
            if enabled:
                st.page_link(page, label=label, icon=icons[status])
            else:
                st.button(
                    label, icon=icons[status], disabled=True,
                    key=f'step_{index}',
                )


def render_application_shell(
    selected: Any | None, orchestrator: Any | None,
    page_handles: Mapping[str, Any],
) -> None:
    if selected is None or orchestrator is None:
        render_welcome_context(page_handles)
        render_workflow_stepper(None, page_handles)
        return
    project_root = str(selected.project_root)
    record = ProjectStateService(project_root).load()
    render_project_context(project_root, orchestrator)
    render_workflow_stepper(record, page_handles)
