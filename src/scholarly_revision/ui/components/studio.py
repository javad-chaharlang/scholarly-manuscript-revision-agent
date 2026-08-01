'''Native Streamlit components used across the Phase 9 workspace.'''
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import streamlit as st
from scholarly_revision.services.gap_analysis_service import read_json

def page_header(title: str, description: str, *, icon: str = ':material/article:') -> None:
    with st.container(horizontal=True, vertical_alignment='center'):
        st.markdown(f'## {icon} {title}')
    st.caption(description)

def empty_state(title: str, message: str, *, icon: str = ':material/inbox:') -> None:
    with st.container(border=True):
        st.subheader(title, anchor=False)
        st.info(message, icon=icon)

def banner(kind: str, message: str) -> None:
    method = {'success': st.success, 'warning': st.warning,
              'blocker': st.error, 'information': st.info}[kind]
    icon = {'success': ':material/check_circle:', 'warning': ':material/warning:',
            'blocker': ':material/error:', 'information': ':material/info:'}[kind]
    with st.container(border=True, key=f'srs_{"info" if kind == "information" else kind}'):
        method(message, icon=icon)

def kpis(items: Iterable[tuple[str, Any, str | None]]) -> None:
    with st.container(horizontal=True):
        for label, value, help_text in items:
            st.metric(label, value, help=help_text, border=True)

def load_json(path: str | Path, default: Any) -> Any:
    source = Path(path)
    if not source.is_file():
        return default
    try:
        return read_json(source)
    except (OSError, ValueError):
        return default

def download(path: str | Path, label: str, key: str, *, disabled: bool = False) -> None:
    source = Path(path)
    st.download_button(label, data=source.read_bytes() if source.is_file() else b'',
                       file_name=source.name, mime='application/octet-stream',
                       icon=':material/download:', key=key,
                       disabled=disabled or not source.is_file())

def state_banner(orchestrator: Any, project_root: str | Path) -> dict[str, Any]:
    data = orchestrator.dashboard(project_root)
    if data.get('project_status') == 'BLOCKED':
        banner('blocker', ' · '.join(data.get('blockers') or ['Project is blocked.']))
    elif data.get('project_status') == 'RELEASED':
        banner('success', 'This project has an immutable local release.')
    return data

def safe_text(value: Any) -> str:
    return '' if value is None else str(value)
