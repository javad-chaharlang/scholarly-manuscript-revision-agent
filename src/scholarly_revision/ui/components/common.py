'''Shared Streamlit presentation helpers.'''

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.i18n import status_label, t
from scholarly_revision.ui.state import redact_exception, set_active_project


def page_title(title: str, description: str) -> None:
    st.title(title)
    st.caption(description)


def project_status_banner(orchestrator: Any, project_root: str) -> None:
    status = orchestrator.dashboard(project_root)
    state = status.get('project_status')
    if state == 'BLOCKED':
        st.error('Project blocked: ' + ', '.join(status.get('blockers', [])))
    elif state == 'RELEASED':
        st.success('Project released as an immutable local package.')
    else:
        st.info('State: ' + str(state))
        st.caption('Next: ' + str(status.get('next_recommended_action')))


def render_project_selector(orchestrator: Any) -> Any:
    projects = orchestrator.registry.list_projects()
    if not projects:
        st.sidebar.info(
            t('no_recent_projects', st.session_state),
            icon=':material/folder_off:',
        )
        return None
    by_label = {
        f'{item.project_name} · {item.manuscript_id} · '
        f'{status_label(item.state, st.session_state)}': item
        for item in projects
    }
    selected = by_label[
        st.sidebar.selectbox(t('project', st.session_state), list(by_label))
    ]
    set_active_project(
        st.session_state, project_id=selected.project_id,
        project_root=selected.project_root,
    )
    return selected


def action_button(
    label: str, action: str, allowed: dict[str, bool], callback: Callable[[], Any],
    *, key: str, help_text: str | None = None,
) -> Any | None:
    if not st.button(
        label, key=key, disabled=not allowed.get(action, False), help=help_text,
    ):
        return None
    try:
        result = callback()
    except Exception as exc:
        st.error(redact_exception(exc))
        return None
    st.success(f'{label} completed.')
    return result


def download_path(path: str | Path, *, label: str, key: str, disabled: bool = False) -> None:
    source = Path(path)
    if source.is_file():
        st.download_button(
            label, data=source.read_bytes(), file_name=source.name,
            mime='application/octet-stream', key=key, disabled=disabled,
        )


def json_rows(path: str | Path, *keys: str) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        return []
    payload: Any = read_json(source)
    for key in keys:
        if not isinstance(payload, dict):
            return []
        payload = payload.get(key, [])
    return payload if isinstance(payload, list) else []
