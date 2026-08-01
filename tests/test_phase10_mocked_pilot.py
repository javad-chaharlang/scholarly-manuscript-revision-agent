from __future__ import annotations

import json
from pathlib import Path

from scholarly_revision.models.agent_run import AgentAuthorDecision
from scholarly_revision.models.agent_task import (
    AgentTaskStatus, AgentTaskType, TransmissionDecision,
)
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.services.agent_worker_service import AgentWorkerService
from scholarly_revision.services.codex_bridge_service import CodexExecutionResult
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.tools.codex_capability_detector import CodexCapabilities
from scholarly_revision.workflows.revision_execution_workflow import prepare_revision_drafts
from tests.phase5_helpers import make_phase5_project


def _capabilities() -> CodexCapabilities:
    return CodexCapabilities(
        executable='mock-codex', installed=True, version='codex-cli mocked',
        authentication_healthy=True, authentication_message='mock authenticated',
        exec_available=True, supports_jsonl=True, supports_output_schema=True,
        supports_output_last_message=True, supports_ephemeral=True,
        supports_cd=True, supports_sandbox=True, supports_color=True,
        supports_skip_git_repo_check=True, help_text_sha256='0' * 64,
    )


def test_mocked_real_project_runs_four_governed_semantic_tasks(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_phase5_project(tmp_path, action_count=1)
    ProjectStateService(root).initialize(root.name, actor='Synthetic Author')
    prepare_revision_drafts(root)
    comments = read_json(root / 'working' / 'reviewer_comments.json')
    comment = comments[0]
    plan = read_json(root / 'working' / 'revision_plan.json')
    approved_action = plan['actions'][0]
    template = read_json(root / 'working' / 'revision_draft_template.json')
    draft = dict(template['drafts'][0]['draft'])
    source = root / 'input' / read_json(root / 'audit' / 'intake_report.json')[
        'input_file_inventory'
    ][1]['name']
    source_hash = sha256_file(source)
    outputs = {}
    mock_stdout = '\n'.join([
        json.dumps({'type': 'thread.started', 'thread_id': 'synthetic'}),
        json.dumps({'type': 'turn.completed'}),
    ])
    mock_stderr = 'anonymous synthetic stderr'

    class MockBridge:
        def __init__(self, *args, **kwargs):
            pass
        def execute(
            self, *, prompt, working_directory, output_schema_path,
            output_last_message_path, cancellation_requested,
        ):
            del working_directory, output_schema_path, cancellation_requested
            task_id = next(
                line.split(':', 1)[1].strip()
                for line in prompt.splitlines() if line.startswith('TASK ID:')
            )
            Path(output_last_message_path).write_text(
                json.dumps(outputs[task_id]), encoding='utf-8',
            )
            return CodexExecutionResult(
                argv=('mock-codex', 'exec', '-'), exit_code=0,
                stdout=mock_stdout, stderr=mock_stderr,
                duration_seconds=0.01, codex_pid=101,
                structured_mode='OUTPUT_SCHEMA_JSONL',
            )

    import scholarly_revision.services.agent_worker_service as worker_module
    monkeypatch.setattr(
        worker_module, 'detect_codex_capabilities',
        lambda *args, **kwargs: _capabilities(),
    )
    monkeypatch.setattr(worker_module, 'CodexBridgeService', MockBridge)
    service = AgentTaskService(root)

    def execute(task, payload):
        service.prepare_context(task.task_id)
        try:
            service.queue(task.task_id, actor='Synthetic Author')
            raise AssertionError('queue bypassed transmission approval')
        except PermissionError:
            pass
        service.transmission_decision(
            task.task_id, TransmissionDecision.APPROVE_TRANSMISSION,
            actor='Synthetic Author',
        )
        service.queue(task.task_id, actor='Synthetic Author')
        outputs[task.task_id] = payload
        assert AgentWorkerService(root).run(task.task_id) == 0
        assert service.registry.load_task(task.task_id).status is AgentTaskStatus.AUTHOR_REVIEW
        service.decide_output(
            task.task_id, AgentAuthorDecision.APPROVE_IMPORT,
            actor='Synthetic Author',
        )
        service.mark_imported(task.task_id, actor='Synthetic Author')
        assert service.registry.load_task(task.task_id).status is AgentTaskStatus.IMPORTED

    gap_task = service.create_task(
        task_type=AgentTaskType.GAP_ANALYSIS, purpose='Mocked gap analysis',
        created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
    )
    execute(gap_task, {'assessments': [{
        'comment_id': comment['comment_id'],
        'original_comment': comment['original_comment'],
        'coverage_status': 'NOT_ADDRESSED',
        'interpretation': 'The requested clarification is absent.',
    }]})

    element = approved_action['target_object']
    target_section = approved_action['target_section']
    plan_task = service.create_task(
        task_type=AgentTaskType.REVISION_PLAN_DRAFT,
        purpose='Mocked plan draft', created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
        source_element_ids=[element],
    )
    execute(plan_task, {'actions': [{
        'action_id': 'ACT-AGENT-MOCK',
        'comment_ids': [comment['comment_id']],
        'change_type': 'GENERAL_CORRECTION',
        'target_section': target_section,
        'target_object': element,
        'rationale': 'A narrow clarification is required.',
        'evidence_requirements': [],
        'unresolved_questions': ['Author wording decision remains required.'],
        'status': 'PLANNED', 'approval_state': 'PENDING',
    }]})

    draft['proposed_text'] = 'Anonymous synthetic clarification for author review.'
    draft['draft_status'] = 'DRAFTED'
    text_task = service.create_task(
        task_type=AgentTaskType.REVISION_TEXT_DRAFT,
        purpose='Mocked revision text', created_by='Synthetic Author',
        related_comment_ids=draft['comment_ids'],
        related_action_ids=[draft['action_id']],
        source_element_ids=draft['target_element_ids'],
    )
    execute(text_task, {'drafts': [draft]})

    response_task = service.create_task(
        task_type=AgentTaskType.RESPONSE_LETTER_DRAFT,
        purpose='Mocked response draft', created_by='Synthetic Author',
        related_comment_ids=[comment['comment_id']],
    )
    execute(response_task, {'entries': [{
        'response_entry_id': 'RESP-AGENT-MOCK',
        'reviewer_source': comment['reviewer_source'],
        'reviewer_number': comment['reviewer_number'],
        'comment_id': comment['comment_id'],
        'sequence_number': comment['sequence_number'],
        'exact_comment': comment['original_comment'],
        'author_response': 'Thank you. This response remains a draft for author review.',
        'changes_made': '', 'verified_locations': [],
        'related_action_ids': [], 'related_change_ids': [],
        'related_evidence_ids': [], 'related_reference_ids': [],
        'highlight': comment['highlight'], 'response_status': 'DRAFTED',
        'location_status': 'UNVERIFIED', 'evidence_status': 'NOT_REQUIRED',
        'author_approved': False,
    }]})

    assert sha256_file(source) == source_hash
    runs = service.registry.runs()
    assert len(runs) == 4
    assert all(run.status.value == 'IMPORTED' for run in runs)
    for run in runs:
        run_dir = service.registry.run_dir(run.run_id)
        assert (run_dir / 'raw_stdout.txt').read_text() == mock_stdout
        assert (run_dir / 'events.jsonl').read_text() == mock_stdout
        assert (run_dir / 'raw_stderr.txt').read_text() == mock_stderr
        assert (run_dir / 'raw_last_message.txt').is_file()
        details = read_json(run_dir / 'validation_report.json')['structured_output']
        assert details['source'] == 'last_message'
    restarted = AgentTaskService(root)
    assert len(restarted.registry.tasks()) == 4
