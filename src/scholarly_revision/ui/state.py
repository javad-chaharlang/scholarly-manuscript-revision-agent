'''Pure session-state and upload helpers used by Streamlit pages.'''

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, MutableMapping


SESSION_DEFAULTS: dict[str, Any] = {
    'workspace_root': '',
    'project_id': None,
    'project_root': None,
    'actor': '',
    'ui_language': 'en',
}


def initialize_session(state: MutableMapping[str, Any]) -> None:
    for key, value in SESSION_DEFAULTS.items():
        if key not in state:
            state[key] = value


def set_active_project(
    state: MutableMapping[str, Any], *, project_id: str, project_root: str | Path,
) -> None:
    state['project_id'] = project_id
    state['project_root'] = str(Path(project_root).resolve())


def clear_active_project(state: MutableMapping[str, Any]) -> None:
    state['project_id'] = None
    state['project_root'] = None


def action_enabled(actions: dict[str, bool], action: str) -> bool:
    return bool(actions.get(action, False))


def safe_upload_name(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r'[^A-Za-z0-9._ -]+', '_', base).strip(' .')
    if not cleaned or cleaned in {'.', '..'}:
        raise ValueError('uploaded file has no safe file name')
    return cleaned


def save_uploaded_file(upload: Any, directory: str | Path) -> Path:
    '''Materialize one upload in a unique staging directory, never over a file.'''

    target_dir = Path(directory).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_upload_name(str(upload.name))
    if target.exists():
        raise FileExistsError(f'staging file already exists: {target.name}')
    payload = upload.getvalue()
    if not payload:
        raise ValueError(f'uploaded file is empty: {target.name}')
    target.write_bytes(payload)
    return target


def project_label(entry: Any) -> str:
    return f'{entry.project_name} · {entry.manuscript_id} · {entry.state.value}'


def redact_exception(exc: Exception) -> str:
    '''Avoid exposing values commonly associated with secrets in UI errors.'''

    message = str(exc)
    message = re.sub(
        r'(?i)(api[_ -]?key|password|secret|token)\s*[:=]\s*\S+',
        r'\1=[REDACTED]', message,
    )
    return f'{type(exc).__name__}: {message}'
