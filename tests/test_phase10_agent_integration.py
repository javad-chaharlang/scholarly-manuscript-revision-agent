from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_run import AgentRunStatus
from scholarly_revision.models.agent_task import (
    AgentTaskStatus, AgentTaskType, TransmissionDecision,
)
from scholarly_revision.services.agent_output_validation_service import AgentOutputValidationService
from scholarly_revision.services.agent_run_registry import AgentRunRegistry
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.services.codex_bridge_service import CodexBridgeService
from scholarly_revision.services.orchestrator_service import NewProjectRequest, OrchestratorService
from scholarly_revision.services.real_project_checklist_service import RealProjectChecklistService
from scholarly_revision.tools.codex_capability_detector import (
    CodexCapabilities, detect_codex_capabilities, detect_codex_executable,
)
from scholarly_revision.tools.prompt_package_builder import build_prompt_package
from scholarly_revision.tools.structured_output_reader import (
    StructuredOutputError, read_structured_output,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'


@pytest.fixture
def project(tmp_path: Path) -> Path:
    workspace = tmp_path / 'private-workspace'
    service = OrchestratorService(workspace)
    state = service.create_project(NewProjectRequest(
        workspace_root=workspace, project_name='Synthetic Agent Project',
        manuscript_id='SYN-AGENT', manuscript_title='Anonymous synthetic manuscript',
        journal='Synthetic Journal', revision_round=1, reviewer_count=2,
        manuscript_language='English', response_language='English',
        citation_style='numeric', result_status='DRAFT',
        reviewer_file=FIXTURES / 'synthetic_reviewer_comments.docx',
        manuscript_file=FIXTURES / 'synthetic_manuscript.docx',
    ), actor='Synthetic Author')
    return Path(service.registry.get(state.project_id).project_root)


def _caps(executable: str) -> CodexCapabilities:
    return CodexCapabilities(
        executable=executable, installed=True, version='codex-cli test',
        authentication_healthy=True,
        authentication_message='Authenticated Codex session detected.',
        exec_available=True, supports_jsonl=True, supports_output_schema=True,
        supports_output_last_message=True, supports_ephemeral=True,
        supports_cd=True, supports_sandbox=True, supports_color=True,
        supports_skip_git_repo_check=True, help_text_sha256='0' * 64,
    )


def _prepared_gap(project: Path):
    service = AgentTaskService(project)
    comments = json.loads(
        (project / 'working' / 'reviewer_comments.json').read_text(encoding='utf-8')
    )
    comment = comments[0]
    task = service.create_task(
        task_type=AgentTaskType.GAP_ANALYSIS,
        purpose='Assess one anonymous synthetic comment.',
        created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
    )
    context = service.prepare_context(task.task_id)
    return service, task, context, comment


def test_task_types_statuses_and_generated_schemas() -> None:
    assert len(AgentTaskType) == 9
    assert {'WAITING_FOR_TRANSMISSION_APPROVAL', 'AUTHOR_REVIEW', 'IMPORTED'} <= {
        item.value for item in AgentTaskStatus
    }
    for name in ('agent-task', 'agent-run', 'agent-context'):
        payload = json.loads((ROOT / 'schemas' / f'{name}.schema.json').read_text())
        assert payload['additionalProperties'] is False


def test_missing_codex_detection(monkeypatch) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _: None)
    assert detect_codex_executable() is None
    caps = detect_codex_capabilities()
    assert not caps.installed and not caps.exec_available


def test_capability_detection_uses_installed_help(tmp_path: Path) -> None:
    executable = tmp_path / 'codex.exe'
    executable.write_bytes(b'anonymous test executable')
    def runner(argv, **kwargs):
        del kwargs
        if argv[-1] == '--version':
            return subprocess.CompletedProcess(argv, 0, 'codex-cli test', '')
        if argv[-2:] == ['exec', '--help']:
            return subprocess.CompletedProcess(
                argv, 0,
                'Usage: codex exec --json --output-schema --output-last-message '
                '--ephemeral --cd --sandbox --color --skip-git-repo-check', '',
            )
        return subprocess.CompletedProcess(argv, 0, 'Logged in', '')
    caps = detect_codex_capabilities(executable, runner=runner)
    assert caps.installed and caps.authentication_healthy and caps.exec_available
    assert caps.supports_jsonl and caps.supports_output_schema and caps.supports_cd


class _Process:
    pid = 101
    returncode = 0
    def __init__(self) -> None:
        self.input = None
        self.terminated = False
    def communicate(self, input=None, timeout=None):
        del timeout
        self.input = input
        return json.dumps({'ok': True}), ''
    def terminate(self):
        self.terminated = True
        self.returncode = 143
    def kill(self):
        self.returncode = 137


def test_bridge_uses_safe_argv_stdin_and_no_shell(tmp_path: Path) -> None:
    executable = str(tmp_path / 'codex.exe')
    Path(executable).write_bytes(b'test')
    schema = tmp_path / 'schema.json'
    schema.write_text('{}', encoding='utf-8')
    captured = {}
    process = _Process()
    def factory(argv, **kwargs):
        captured.update({'argv': argv, **kwargs})
        return process
    result = CodexBridgeService(
        capabilities=_caps(executable), popen_factory=factory,
    ).execute(
        prompt='anonymous prompt', working_directory=tmp_path,
        output_schema_path=schema, output_last_message_path=tmp_path / 'out.json',
    )
    assert captured['shell'] is False and captured['argv'][-1] == '-'
    assert '--cd' in captured['argv']
    assert '--skip-git-repo-check' in captured['argv']
    assert process.input == 'anonymous prompt'
    assert json.loads(result.stdout) == {'ok': True}
    assert all('anonymous prompt' != item for item in captured['argv'])


def test_bridge_cancellation_terminates_process(tmp_path: Path) -> None:
    executable = str(tmp_path / 'codex.exe')
    Path(executable).write_bytes(b'test')
    process = _Process()
    result = CodexBridgeService(
        capabilities=_caps(executable), popen_factory=lambda *a, **k: process,
    ).execute(
        prompt='anonymous', working_directory=tmp_path,
        cancellation_requested=lambda: True,
    )
    assert result.cancelled and process.terminated


def test_json_and_jsonl_reader_is_strict() -> None:
    assert read_structured_output(
        last_message_path=None, raw_stdout=json.dumps({'value': 1}), jsonl=False,
    ) == {'value': 1}
    assert read_structured_output(
        last_message_path=None,
        raw_stdout=json.dumps({
            'type': 'item.completed',
            'item': {
                'type': 'agent_message',
                'text': json.dumps({'value': 2}),
            },
        }),
        jsonl=True,
    ) == {'value': 2}
    with pytest.raises(StructuredOutputError):
        read_structured_output(
            last_message_path=None, raw_stdout='not json', jsonl=False,
        )


def test_transmission_gate_persistence_duplicate_and_prompt_hash(project: Path) -> None:
    service, task, context, _ = _prepared_gap(project)
    with pytest.raises(PermissionError):
        service.queue(task.task_id, actor='Synthetic Author')
    with pytest.raises(ValueError, match='duplicate'):
        service.create_task(
            task_type=AgentTaskType.GAP_ANALYSIS, purpose='duplicate',
            created_by='Synthetic Author',
            related_comment_ids=task.related_comment_ids,
        )
    approved = service.transmission_decision(
        task.task_id, TransmissionDecision.APPROVE_TRANSMISSION,
        actor='Synthetic Author',
    )
    run = service.queue(task.task_id, actor='Synthetic Author')
    restored = AgentRunRegistry(project).load_run(run.run_id)
    package = build_prompt_package(approved, context)
    assert restored.prompt_sha256 == package.sha256
    assert (project / 'agent_runs' / run.run_id / 'prompt_hash.txt').read_text().strip() == package.sha256
    assert (project / 'backups' / 'agent_tasks' / run.run_id).is_dir()


def test_context_custom_approval_and_sensitive_redaction(project: Path) -> None:
    service = AgentTaskService(project)
    comments = json.loads(
        (project / 'working' / 'reviewer_comments.json').read_text(encoding='utf-8')
    )
    task = service.create_task(
        task_type=AgentTaskType.GENERAL_RESEARCH_NOTE,
        purpose='Anonymous note', created_by='Synthetic Author',
        related_comment_ids=[comments[0]['comment_id']],
        context_policy=ContextPolicy.CUSTOM_AUTHOR_APPROVED_CONTEXT,
    )
    with pytest.raises(ValueError, match='explicit'):
        service.prepare_context(
            task.task_id, custom_payload={'author_email': 'person@example.org'},
        )
    context = service.prepare_context(
        task.task_id,
        custom_payload={
            'author_email': 'person@example.org',
            'note': 'Call +1 202 555 0199; path C:\\Private\\paper.docx; '
                    'sk-abcdefghijklmnop',
        },
        custom_context_approved=True,
    )
    serialized = json.dumps(context.transmitted_payload)
    assert context.transmitted_payload['author_email'] == '[REDACTED]'
    assert 'example.org' not in serialized and 'sk-' not in serialized
    assert context.redactions and context.total_character_count > 0


def test_pilot_mode_limits_scope_and_requires_named_full_approval(project: Path) -> None:
    service = AgentTaskService(project)
    comments = json.loads(
        (project / 'working' / 'reviewer_comments.json').read_text(encoding='utf-8')
    )
    with pytest.raises(ValueError, match='Pilot Mode'):
        service.create_task(
            task_type=AgentTaskType.GAP_ANALYSIS, purpose='too broad',
            created_by='Synthetic Author',
            related_comment_ids=[item['comment_id'] for item in comments[:4]],
        )
    with pytest.raises(ValueError):
        RealProjectChecklistService(project).record_pilot_approval(
            actor='', checks={},
        )


def test_gap_validation_requires_coverage_and_rejects_invented_evidence(project: Path) -> None:
    service, task, context, comment = _prepared_gap(project)
    validator = AgentOutputValidationService(project)
    valid = validator.validate(task, context, {'assessments': [{
        'comment_id': comment['comment_id'],
        'original_comment': comment['original_comment'],
        'coverage_status': 'NOT_ADDRESSED',
        'interpretation': 'Evidence is missing.',
    }]})
    assert valid.valid
    assert not validator.validate(task, context, {'assessments': []}).valid
    note = service.create_task(
        task_type=AgentTaskType.GENERAL_RESEARCH_NOTE,
        purpose='Check evidence IDs', created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
    )
    note_context = service.prepare_context(note.task_id)
    invented = validator.validate(note, note_context, {'notes': [{
        'record_id': 'NOTE-A', 'related_comment_ids': [comment['comment_id']],
        'analysis': 'Evidence is absent.', 'evidence_ids': ['E-FAKE'],
        'uncertainties': ['Source unavailable.'],
    }]})
    assert not invented.valid
    assert 'INVENTED_EVIDENCE' in {item['code'] for item in invented.errors}


def test_unknown_comment_and_additional_fields_rejected(project: Path) -> None:
    service, _, _, comment = _prepared_gap(project)
    note = service.create_task(
        task_type=AgentTaskType.GENERAL_RESEARCH_NOTE,
        purpose='Strict note', created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
    )
    context = service.prepare_context(note.task_id)
    result = AgentOutputValidationService(project).validate(note, context, {
        'notes': [{
            'record_id': 'NOTE-B', 'related_comment_ids': ['R9-C99'],
            'analysis': 'Unknown link.', 'evidence_ids': [], 'uncertainties': [],
            'unsupported': True,
        }],
    })
    assert not result.valid


def test_interrupted_run_requires_recovery_not_resume(project: Path) -> None:
    service, task, _, _ = _prepared_gap(project)
    service.transmission_decision(
        task.task_id, TransmissionDecision.APPROVE_TRANSMISSION,
        actor='Synthetic Author',
    )
    run = service.queue(task.task_id, actor='Synthetic Author')
    registry = AgentRunRegistry(project)
    old = run.created_at
    registry.save_run(registry.load_run(run.run_id).model_copy(update={
        'status': AgentRunStatus.RUNNING, 'updated_at': old,
        'started_at': old, 'worker_pid': 99999999,
    }))
    recovered = registry.recover_interrupted(stale_seconds=0)
    assert recovered == [run.run_id]
    assert registry.load_run(run.run_id).status is AgentRunStatus.RECOVERY_REQUIRED
    assert registry.load_task(task.task_id).status is AgentTaskStatus.BLOCKED


def test_checklist_detects_immutable_intake_sources(project: Path) -> None:
    report = RealProjectChecklistService(project).evaluate()
    by_id = {item['check_id']: item for item in report['items']}
    assert by_id['source_files_copied_and_hashed']['complete']
    assert by_id['comments_extracted']['complete']
    assert not by_id['release_permitted']['complete']


def test_no_api_key_direct_api_telemetry_or_agent_word_mutation() -> None:
    paths = list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    text = '\n'.join(path.read_text(encoding='utf-8') for path in paths)
    assert 'OPENAI_API_KEY' not in text
    assert 'from openai import' not in text and 'import openai' not in text
    assert 'import opentelemetry' not in text.casefold()
    assert 'sentry_sdk' not in text.casefold()
    agent_sources = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (ROOT / 'src' / 'scholarly_revision').rglob('agent*.py')
    )
    assert 'Document(' not in agent_sources
    assert 'docx_revision_applier' not in agent_sources


def test_agent_task_ui_exposes_gates_and_disables_run(project: Path) -> None:
    testing = pytest.importorskip('streamlit.testing.v1')
    _, task, _, _ = _prepared_gap(project)
    def page(raw_project):
        from pathlib import Path
        from scholarly_revision.services.orchestrator_service import OrchestratorService
        from scholarly_revision.ui.pages.agent_tasks_v9 import render
        selected = Path(raw_project)
        render(OrchestratorService(selected.parent), raw_project, 'Synthetic Author')
    app = testing.AppTest.from_function(
        page, args=(str(project),), default_timeout=30,
    ).run(timeout=30)
    assert not app.exception
    buttons = {item.label: item for item in app.button}
    assert {'Prepare Context', 'Review Context', 'Run with Codex',
            'Retry with Instruction'} <= set(buttons)
    assert buttons['Run with Codex'].disabled
    assert any(
        task.task_id in option
        for box in app.selectbox for option in box.options
    )
