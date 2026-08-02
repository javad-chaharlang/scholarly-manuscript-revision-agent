from __future__ import annotations
from pathlib import Path
import tomllib
import pytest
from scholarly_revision.models.project_state import ProjectState, ProjectStateRecord
from scholarly_revision.services.orchestrator_service import NewProjectRequest, OrchestratorService
from scholarly_revision.ui.design_tokens import COLORS
from scholarly_revision.ui.i18n import TRANSLATIONS, is_rtl
from scholarly_revision.ui.layout import (
    quick_action_states, state_progress, workflow_step_states,
)
from scholarly_revision.ui.navigation import (
    NAVIGATION_GROUPS, NAVIGATION_ORDER, PAGE_SPECS,
    navigation_state, page_available,
)
from scholarly_revision.ui.pages.dashboard_v9 import APPLICATION_VERSION
from scholarly_revision.ui.project_data import recent_project_snapshots
from scholarly_revision.ui.theme import _BASE_CSS, _RTL_ENHANCEMENT_CSS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'

def _render_page(module_name: str, workspace: str, project_root: str) -> None:
    import importlib
    from scholarly_revision.services.orchestrator_service import OrchestratorService
    module = importlib.import_module(module_name)
    module.render(OrchestratorService(workspace), project_root, 'Synthetic Author')

def _project(tmp_path: Path):
    workspace = tmp_path / 'private-workspace'
    service = OrchestratorService(workspace)
    state = service.create_project(NewProjectRequest(
        workspace_root=workspace, project_name='Synthetic UI', manuscript_id='SYN-UI',
        manuscript_title='Anonymous synthetic manuscript', journal='Synthetic Journal',
        revision_round=1, reviewer_count=2, manuscript_language='English',
        response_language='English', citation_style='numeric', result_status='DRAFT',
        reviewer_file=FIXTURES / 'synthetic_reviewer_comments.docx',
        manuscript_file=FIXTURES / 'synthetic_manuscript.docx'), actor='Synthetic Author')
    return workspace, service, service.registry.get(state.project_id), state

def test_navigation_order_groups_icons_and_paths() -> None:
    assert NAVIGATION_ORDER == (
        'Dashboard', 'Projects', 'New Project', 'Input Files', 'Reviewer Comments',
        'Gap Analysis', 'Revision Plan', 'Text Approval', 'Manuscript Versions',
        'Reference Audit', 'Scientific QA', 'Response Letter', 'Visual QA',
        'Final Release', 'Audit Timeline', 'Settings')
    assert NAVIGATION_GROUPS == ('Overview', 'Intake & Analysis', 'Revision',
                                 'Quality Assurance', 'Release', 'System')
    assert all(spec.icon.startswith(':material/') for spec in PAGE_SPECS)
    assert len({spec.url_path for spec in PAGE_SPECS}) == len(PAGE_SPECS)

def test_state_navigation_and_stepper_disable_future_pages() -> None:
    assert page_available('dashboard', None, project_selected=False)
    assert not page_available('final_release', ProjectState.INTAKE_REVIEW, project_selected=True)
    record = ProjectStateRecord(project_id='synthetic', state=ProjectState.INTAKE_REVIEW,
        next_required_action='Review', sequence=1, updated_at='2026-01-01T00:00:00Z')
    steps = workflow_step_states(record)
    assert next(i for i in steps if i['label'] == 'Comment Review')['state'] == 'active'
    assert next(i for i in steps if i['label'] == 'Release')['enabled'] is False
    assert state_progress(ProjectState.RELEASED) == 100


def test_all_workflow_steps_visible_and_warning_supported() -> None:
    pending = workflow_step_states(None)
    assert [item['label'] for item in pending] == [
        'Intake', 'Comment Review', 'Gap Analysis', 'Plan Approval', 'Drafting',
        'Text Approval', 'Revision Application', 'Scientific QA', 'Response',
        'Visual QA', 'Release',
    ]
    assert len(pending) == 11
    assert all(item['state'] == 'pending' and not item['enabled'] for item in pending)
    record = ProjectStateRecord(
        project_id='synthetic', state=ProjectState.INTAKE_REVIEW,
        next_required_action='Review', sequence=1,
        updated_at='2026-01-01T00:00:00Z',
    )
    warning = workflow_step_states(
        record, warning_steps={ProjectState.INTAKE_REVIEW},
    )
    assert warning[1]['state'] == 'warning' and warning[1]['enabled']


def test_quick_actions_are_state_aware() -> None:
    empty = {
        item['label_key']: item['enabled']
        for item in quick_action_states(None, project_selected=False)
    }
    assert empty['new_project_action']
    assert not any(value for key, value in empty.items() if key != 'new_project_action')
    review = ProjectStateRecord(
        project_id='synthetic', state=ProjectState.INTAKE_REVIEW,
        next_required_action='Review', sequence=1,
        updated_at='2026-01-01T00:00:00Z',
    )
    actions = {
        item['label_key']: item['enabled']
        for item in quick_action_states(review, project_selected=True)
    }
    assert actions['resume_project'] and actions['review_comments_action']
    assert not actions['build_release'] and not actions['run_qa']


def test_active_navigation_state_is_explicit() -> None:
    items = navigation_state('dashboard', None, project_selected=False)
    assert sum(bool(item['active']) for item in items) == 1
    dashboard = next(item for item in items if item['key'] == 'dashboard')
    release = next(item for item in items if item['key'] == 'final_release')
    assert dashboard['active'] and dashboard['available']
    assert not release['active'] and not release['available']

def test_design_tokens_reviewer_policy_and_localization() -> None:
    assert COLORS.navy == '#0F172A' and COLORS.indigo == '#4F46E5'
    assert (COLORS.reviewer_1, COLORS.reviewer_2, COLORS.shared) == ('#FFFF00', '#00FF00', '#EE82EE')
    assert TRANSLATIONS['en']['dashboard'] == 'Dashboard'
    assert TRANSLATIONS['fa']['dashboard'] == 'داشبورد'
    assert is_rtl({'ui_language': 'fa'}) and not is_rtl({'ui_language': 'en'})

def test_telemetry_theme_and_no_external_http_calls() -> None:
    config = tomllib.loads((ROOT / '.streamlit' / 'config.toml').read_text(encoding='utf-8'))
    assert config['browser']['gatherUsageStats'] is False
    assert 'light' in config['theme'] and 'dark' in config['theme']
    sources = '\n'.join(path.read_text(encoding='utf-8') for path in
                        (ROOT / 'src' / 'scholarly_revision' / 'ui').rglob('*.py'))
    assert 'import requests' not in sources and 'from requests' not in sources
    assert 'import httpx' not in sources and 'from httpx' not in sources
    assert 'https://' not in sources and 'http://' not in sources

def test_project_creation_resume_selector_metrics_and_privacy(tmp_path: Path) -> None:
    workspace, service, entry, state = _project(tmp_path)
    assert ROOT not in Path(entry.project_root).parents
    assert OrchestratorService(workspace).resume(entry.project_id).state is state.state
    assert service.dashboard(entry.project_root)['total_comments'] > 0
    assert service.available_actions(entry.project_root)['apply_revisions'] is False


def test_recent_project_cards_use_safe_metadata_only(tmp_path: Path) -> None:
    _, service, _, _ = _project(tmp_path)
    rows = recent_project_snapshots(service)
    assert len(rows) == 1
    row = rows[0]
    assert {
        'project_name', 'manuscript_id', 'journal', 'state', 'progress',
        'blocker_count', 'readiness', 'last_modified',
    } <= set(row)
    assert row['project_name'] == 'Synthetic UI'
    assert 'manuscript_text' not in row
    assert 'reviewer_comment' not in row


def test_desktop_responsive_css_has_safe_widths_and_focus_states() -> None:
    assert 'max-width: 1500px' in _BASE_CSS
    assert '@media (max-width: 900px)' in _BASE_CSS
    assert 'overflow-x: clip' in _BASE_CSS
    assert 'focus-visible' in _BASE_CSS
    assert 'stNavigation' in _BASE_CSS
    assert APPLICATION_VERSION

def test_dashboard_apptest_without_project() -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    from scripts.run_app import APP
    app = testing.AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception
    markdown = [item.value for item in app.markdown]
    subheaders = [item.value for item in app.subheader]
    buttons = {item.label: item for item in app.button}
    assert any('Scholarly Revision Studio' in value for value in markdown)
    assert {'Getting started', 'Recent projects', 'Workflow overview',
            'Required-input checklist', 'System readiness'} <= set(subheaders)
    assert {'Create New Project', 'Open Existing Project',
            'Configure Workspace'} <= set(buttons)
    assert len([label for label in buttons if label[:2].rstrip('.').isdigit()]) >= 9
    assert 'Application version' in ' '.join(item.value for item in app.caption)
    assert len(app.sidebar.text_input) == 2

def test_dashboard_apptest_with_project(tmp_path: Path) -> None:
    workspace, _, _, _ = _project(tmp_path)
    testing = pytest.importorskip('streamlit.testing.v1')
    from scripts.run_app import APP
    app = testing.AppTest.from_file(str(APP)).run(timeout=30)
    app.sidebar.text_input[1].set_value(str(workspace)).run(timeout=30)
    assert not app.exception
    assert app.sidebar.selectbox
    assert any(
        'Anonymous synthetic manuscript' in item.value
        for item in app.markdown
    )
    assert any('SYN-UI' in item.value for item in app.caption)
    assert any('Synthetic UI' in item.value for item in app.markdown)
    assert any(item.label == 'Resume' for item in app.button)
    assert any('Project context' in item.value for item in app.sidebar.markdown)

def test_all_phase9_page_modules_import() -> None:
    import importlib
    for spec in PAGE_SPECS:
        suffix = '_v9' if spec.key in {'dashboard', 'new_project', 'input_files',
            'reviewer_comments', 'gap_analysis', 'revision_plan', 'text_approval',
            'manuscript_versions', 'reference_audit', 'scientific_qa',
            'response_letter', 'visual_qa', 'final_release', 'settings'} else ''
        module = importlib.import_module(f'scholarly_revision.ui.pages.{spec.module}{suffix}')
        assert callable(module.render)

def test_bilingual_switching_apptest() -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    from scripts.run_app import APP
    app = testing.AppTest.from_file(str(APP)).run(timeout=30)
    app.sidebar.segmented_control[0].set_value('فارسی').run(timeout=30)
    assert not app.exception
    assert any('استودیوی بازنگری علمی' in item.value for item in app.markdown)
    assert any(item.label == 'ایجاد پروژه جدید' for item in app.button)
    assert any('شروع کار' in item.value for item in app.subheader)
    assert 'stSidebar' in _RTL_ENHANCEMENT_CSS
    assert 'unicode-bidi: plaintext' in _RTL_ENHANCEMENT_CSS

def test_all_pages_load_for_synthetic_project(tmp_path: Path) -> None:
    import importlib
    testing = pytest.importorskip('streamlit.testing.v1')
    workspace, service, entry, _ = _project(tmp_path)
    v9 = {'dashboard', 'new_project', 'input_files', 'reviewer_comments',
          'gap_analysis', 'revision_plan', 'text_approval', 'manuscript_versions',
          'reference_audit', 'scientific_qa', 'response_letter', 'visual_qa',
          'final_release', 'settings'}
    for spec in PAGE_SPECS:
        suffix = '_v9' if spec.key in v9 else ''
        module = importlib.import_module(f'scholarly_revision.ui.pages.{spec.module}{suffix}')
        app = testing.AppTest.from_function(
            _render_page, args=(module.__name__, str(workspace), entry.project_root),
            default_timeout=30).run(timeout=30)
        assert not app.exception, spec.title

def test_wizard_rejects_zero_byte_and_builds_resumable_project(tmp_path: Path, monkeypatch) -> None:
    from scholarly_revision.ui.pages import new_project_v9 as wizard
    from scholarly_revision.services.wizard_upload_service import (
        REVIEWER_ROLE, MANUSCRIPT_ROLE, WizardUploadError,
        create_draft_directory, persist_upload,
    )
    draft_id, draft = create_draft_directory(draft_root=tmp_path / 'drafts')
    with pytest.raises(WizardUploadError, match='empty'):
        persist_upload(
            payload=b'', original_name='empty.docx',
            mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            role=REVIEWER_ROLE, draft_directory=draft)
    workspace = tmp_path / 'wizard-workspace'
    reviewer_record = persist_upload(
        payload=(FIXTURES / 'synthetic_reviewer_comments.docx').read_bytes(),
        original_name='reviewers.docx', mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        role=REVIEWER_ROLE, draft_directory=draft)
    manuscript_record = persist_upload(
        payload=(FIXTURES / 'synthetic_manuscript.docx').read_bytes(),
        original_name='manuscript.docx', mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        role=MANUSCRIPT_ROLE, draft_directory=draft)
    data = {
        'new_project_draft_id': draft_id,
        'new_project_draft_directory': str(draft),
        'wiz_project_name': 'Wizard synthetic', 'wiz_manuscript_id': 'WIZ-SYN',
        'wiz_title': 'Anonymous wizard manuscript', 'wiz_journal': 'Synthetic Journal',
        'wiz_round': 1, 'wiz_reviewer_count': 2, 'wiz_manuscript_language': 'English',
        'wiz_response_language': 'English', 'wiz_citation_style': 'numeric',
        'wiz_result_status': 'DRAFT',
        'new_project_reviewer_upload_record': reviewer_record,
        'new_project_manuscript_upload_record': manuscript_record,
    }
    monkeypatch.setattr(wizard.st, 'session_state', data)
    request = wizard._request(workspace)
    service = OrchestratorService(workspace)
    state = service.create_project(request, actor='Synthetic Author')
    assert OrchestratorService(workspace).resume(state.project_id).state is state.state
    wizard._verify_project_input_hashes(service.registry.get(state.project_id).project_root)


def test_project_archive_is_reversible_and_never_deletes_files(tmp_path: Path) -> None:
    _, service, entry, _ = _project(tmp_path)
    root = Path(entry.project_root)
    archived = service.registry.set_archived(entry.project_id, archived=True)
    assert archived.archived is True
    assert root.is_dir()
    assert service.registry.list_projects() == []
    assert service.registry.list_projects(include_archived=True)[0].project_id == entry.project_id
    restored = service.registry.set_archived(entry.project_id, archived=False)
    assert restored.archived is False
    assert service.registry.list_projects()[0].project_id == entry.project_id
