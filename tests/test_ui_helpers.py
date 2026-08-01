from pathlib import Path

import pytest

from scripts.run_app import APP, build_command
from scholarly_revision.ui.app import PAGES
from scholarly_revision.ui.state import (
    action_enabled, initialize_session, redact_exception, safe_upload_name,
)


def test_session_and_action_helpers() -> None:
    state = {}
    initialize_session(state)
    assert state['project_root'] is None
    assert action_enabled({'run': True}, 'run')
    assert not action_enabled({'run': True}, 'release')
    state['actor'] = 'Synthetic Author'
    initialize_session(state)
    assert state['actor'] == 'Synthetic Author'


def test_upload_names_and_secret_redaction() -> None:
    assert safe_upload_name('../../synthetic.docx') == 'synthetic.docx'
    assert '[REDACTED]' in redact_exception(
        ValueError('api_key=synthetic-secret')
    )


def test_all_pages_and_local_launcher_command() -> None:
    assert len(PAGES) == 16
    assert list(PAGES) == [
        'Dashboard', 'Projects', 'New Project', 'Input Files', 'Reviewer Comments',
        'Gap Analysis', 'Revision Plan', 'Text Approval',
        'Manuscript Versions', 'Reference Audit', 'Scientific QA',
        'Response Letter', 'Visual QA', 'Final Release', 'Audit Timeline', 'Settings',
    ]
    command = build_command(port=8765, headless=True)
    assert str(APP) in command
    assert 'localhost' in command
    assert '8765' in command


def test_streamlit_app_loads_without_browser() -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    app = testing.AppTest.from_file(str(APP))
    app.run(timeout=20)
    assert not app.exception
    assert len(app.sidebar.text_input) == 2
    assert not app.exception
