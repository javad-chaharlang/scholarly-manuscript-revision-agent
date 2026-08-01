'''Governed creation, approval, queueing, retry, and import decisions.'''
from __future__ import annotations
import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from scholarly_revision.models.agent_context import AgentContextManifest, ContextPolicy
from scholarly_revision.models.agent_run import AgentAuthorDecision, AgentRun, AgentRunStatus
from scholarly_revision.models.agent_task import (
    AgentTask, AgentTaskPriority, AgentTaskStatus, AgentTaskType, TransmissionDecision,
)
from scholarly_revision.services.agent_context_service import AgentContextService
from scholarly_revision.services.agent_run_registry import AgentRunRegistry
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.tools.prompt_package_builder import (
    PROMPT_VERSION, build_prompt_package, output_schema_for,
)

@dataclass(frozen=True, slots=True)
class AgentSettings:
    codex_executable: str | None = None
    default_timeout_seconds: int = 300
    context_warning_characters: int = 40000
    global_concurrency: int = 1
    pilot_mode: bool = True
    allow_semantic_tasks: bool = True
    one_active_task_per_project: bool = True
    abandoned_run_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def load_agent_settings(project_root: str | Path) -> AgentSettings:
    root = Path(project_root).expanduser().resolve()
    path = root / 'config' / 'agent_settings.json'
    if not path.is_file():
        return AgentSettings()
    raw = json.loads(path.read_text(encoding='utf-8'))
    allowed = set(AgentSettings.__dataclass_fields__)
    if set(raw) - allowed:
        raise ValueError('agent settings contain unsupported fields')
    return AgentSettings(**raw)

def save_agent_settings(project_root: str | Path, settings: AgentSettings) -> Path:
    root = Path(project_root).expanduser().resolve()
    path = root / 'config' / 'agent_settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(
        json.dumps(settings.to_dict(), indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)
    return path

_DEFAULT_CONTEXT = {
    AgentTaskType.COMMENT_INTERPRETATION: ContextPolicy.MINIMAL_COMMENT_CONTEXT,
    AgentTaskType.GAP_ANALYSIS: ContextPolicy.SECTION_CONTEXT,
    AgentTaskType.REVISION_PLAN_DRAFT: ContextPolicy.EXTENDED_SECTION_CONTEXT,
    AgentTaskType.REVISION_TEXT_DRAFT: ContextPolicy.SECTION_CONTEXT,
    AgentTaskType.REFERENCE_NEED_ANALYSIS: ContextPolicy.REFERENCE_CONTEXT,
    AgentTaskType.SEMANTIC_QA_REVIEW: ContextPolicy.RESULTS_CONTEXT,
    AgentTaskType.RESPONSE_LETTER_DRAFT: ContextPolicy.RESPONSE_CONTEXT,
    AgentTaskType.GENERAL_RESEARCH_NOTE: ContextPolicy.MINIMAL_COMMENT_CONTEXT,
}

def _identifier(prefix: str) -> str:
    return f'{prefix}-{uuid.uuid4().hex[:16].upper()}'

class AgentTaskService:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.registry = AgentRunRegistry(self.root)
        self.contexts = AgentContextService(self.root)
        self.state = ProjectStateService(self.root)

    @property
    def settings(self) -> AgentSettings:
        return load_agent_settings(self.root)

    def create_task(
        self, *, task_type: AgentTaskType | str, purpose: str, created_by: str,
        related_comment_ids: list[str] | None = None,
        related_action_ids: list[str] | None = None,
        source_element_ids: list[str] | None = None,
        context_policy: ContextPolicy | str | None = None,
        priority: AgentTaskPriority | str = AgentTaskPriority.NORMAL,
        retry_of_task_id: str | None = None, retry_instruction: str | None = None,
    ) -> AgentTask:
        settings = self.settings
        if not settings.allow_semantic_tasks:
            raise PermissionError('semantic tasks are disabled in Agent Settings')
        kind = AgentTaskType(task_type)
        comments = list(related_comment_ids or [])
        actions = list(related_action_ids or [])
        elements = list(source_element_ids or [])
        if settings.pilot_mode and len(comments) > 3:
            raise ValueError('Pilot Mode permits one reviewer comment or one small group per task')
        project_id = self.state.load().project_id
        now = datetime.now(UTC)
        schema = output_schema_for(kind)
        policy = ContextPolicy(context_policy or _DEFAULT_CONTEXT[kind])
        task = AgentTask(
            task_id=_identifier('TASK'), project_id=project_id, task_type=kind,
            related_comment_ids=comments, related_action_ids=actions,
            source_element_ids=elements, requested_output_schema=str(schema['title']),
            context_policy=policy.value,
            prompt_template=f'{kind.value.lower()}-v{PROMPT_VERSION}.txt',
            status=AgentTaskStatus.CREATED, priority=AgentTaskPriority(priority),
            approval_required=True, created_by=created_by, created_at=now, updated_at=now,
            purpose=purpose, retry_of_task_id=retry_of_task_id,
            retry_instruction=retry_instruction,
        )
        duplicate = self.registry.find_duplicate(task)
        if duplicate is not None and retry_of_task_id is None:
            raise ValueError(f'duplicate semantic task already exists: {duplicate.task_id}')
        self.registry.add_task(task)
        self._event('AGENT_TASK_CREATED', 'create_agent_task', created_by, task)
        return task

    def prepare_context(
        self, task_id: str, *, custom_payload: dict[str, Any] | None = None,
        custom_context_approved: bool = False,
    ) -> AgentContextManifest:
        task = self.registry.load_task(task_id)
        if task.status not in {
            AgentTaskStatus.CREATED, AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            AgentTaskStatus.CONTEXT_READY,
        }:
            raise ValueError(f'context cannot be prepared in {task.status.value}')
        context = self.contexts.prepare(
            task, custom_payload=custom_payload,
            custom_context_author_approved=custom_context_approved,
        )
        path = self.registry.save_context(context)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        now = datetime.now(UTC)
        updated = task.model_copy(update={
            'status': AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            'updated_at': now, 'context_manifest_sha256': digest,
            'transmission_decision': None, 'transmission_approved_by': None,
            'transmission_approved_at': None,
        })
        self.registry.save_task(updated)
        self._event(
            'AGENT_CONTEXT_PREPARED', 'prepare_agent_context', task.created_by, updated,
            {'context_characters': context.total_character_count,
             'input_hash_count': len(context.input_file_hashes)},
        )
        return context

    def transmission_decision(
        self, task_id: str, decision: TransmissionDecision | str, *, actor: str,
    ) -> AgentTask:
        actor = actor.strip()
        if not actor:
            raise ValueError('a named author is required for a transmission decision')
        task = self.registry.load_task(task_id)
        choice = TransmissionDecision(decision)
        if task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL:
            raise ValueError('transmission decision is available only after context review')
        now = datetime.now(UTC)
        if choice is TransmissionDecision.APPROVE_TRANSMISSION:
            self.registry.load_context(task_id)
            updates = {
                'status': AgentTaskStatus.CONTEXT_READY, 'updated_at': now,
                'transmission_decision': choice, 'transmission_approved_by': actor,
                'transmission_approved_at': now,
            }
        elif choice is TransmissionDecision.MODIFY_CONTEXT:
            updates = {
                'status': AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
                'updated_at': now, 'transmission_decision': choice,
                'transmission_approved_by': None, 'transmission_approved_at': None,
            }
        else:
            updates = {
                'status': AgentTaskStatus.CANCELLED, 'updated_at': now,
                'transmission_decision': choice, 'cancel_requested': True,
            }
        updated = task.model_copy(update=updates)
        self.registry.save_task(updated)
        self._event(
            'AGENT_TRANSMISSION_DECISION', choice.value.lower(), actor, updated,
            {'decision': choice.value},
        )
        return updated

    def queue(self, task_id: str, *, actor: str) -> AgentRun:
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.CONTEXT_READY:
            raise PermissionError('Run with Codex requires explicit transmission approval')
        if task.transmission_decision is not TransmissionDecision.APPROVE_TRANSMISSION:
            raise PermissionError('APPROVE_TRANSMISSION was not recorded')
        context = self.registry.load_context(task_id)
        if not task.context_manifest_sha256:
            raise ValueError('approved context manifest hash is missing')
        prompt = build_prompt_package(task, context)
        now = datetime.now(UTC)
        run = AgentRun(
            run_id=_identifier('RUN'), task_id=task.task_id, project_id=task.project_id,
            status=AgentRunStatus.QUEUED, progress_percent=0, created_at=now, updated_at=now,
            prompt_version=prompt.version, prompt_sha256=prompt.sha256,
            context_manifest_sha256=task.context_manifest_sha256,
            output_schema_name=task.requested_output_schema, structured_mode='AUTO',
        )
        queued_task = task.model_copy(update={
            'status': AgentTaskStatus.QUEUED, 'updated_at': now,
            'active_run_id': run.run_id, 'last_error_code': None, 'last_error_message': None,
        })
        self.registry.create_run(
            run, queued_task, context, prompt=prompt.text, output_schema=prompt.output_schema,
        )
        if self.settings.pilot_mode:
            backup = self.root / 'backups' / 'agent_tasks' / run.run_id
            backup.mkdir(parents=True, exist_ok=False)
            shutil.copy2(self.registry.task_path(task.task_id), backup / 'task-before-queue.json')
            shutil.copy2(
                self.registry.tasks_dir / f'{task.task_id}.context.json',
                backup / 'approved-context.json',
            )
            shutil.copy2(self.registry.run_dir(run.run_id) / 'prompt.txt', backup / 'prompt.txt')
        self.registry.save_task(queued_task)
        self._event('AGENT_RUN_QUEUED', 'queue_agent_run', actor, queued_task, {
            'run_id': run.run_id, 'prompt_version': prompt.version,
        })
        return run

    def modify_context_scope(
        self, task_id: str, *, actor: str,
        related_comment_ids: list[str], related_action_ids: list[str],
        source_element_ids: list[str], context_policy: ContextPolicy | str,
    ) -> AgentTask:
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL:
            raise ValueError('context scope can change only before transmission approval')
        if self.settings.pilot_mode and len(related_comment_ids) > 3:
            raise ValueError('Pilot Mode limits one task to one comment or a small group')
        now = datetime.now(UTC)
        updated = task.model_copy(update={
            'related_comment_ids': related_comment_ids,
            'related_action_ids': related_action_ids,
            'source_element_ids': source_element_ids,
            'context_policy': ContextPolicy(context_policy).value,
            'status': AgentTaskStatus.CREATED, 'updated_at': now,
            'transmission_decision': TransmissionDecision.MODIFY_CONTEXT,
            'transmission_approved_by': None, 'transmission_approved_at': None,
            'context_manifest_sha256': None,
        })
        self.registry.save_task(updated)
        self._event('AGENT_CONTEXT_SCOPE_MODIFIED', 'modify_agent_context', actor, updated)
        return updated

    def cancel(self, task_id: str, *, actor: str) -> AgentTask:
        task = self.registry.load_task(task_id)
        if task.status in {
            AgentTaskStatus.IMPORTED, AgentTaskStatus.REJECTED,
            AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED,
        }:
            raise ValueError(f'task is already terminal: {task.status.value}')
        now = datetime.now(UTC)
        updated = task.model_copy(update={'cancel_requested': True, 'updated_at': now})
        if task.status not in {AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING}:
            updated = updated.model_copy(update={'status': AgentTaskStatus.CANCELLED})
        self.registry.save_task(updated)
        if task.active_run_id:
            run = self.registry.load_run(task.active_run_id)
            self.registry.save_run(run.model_copy(update={
                'cancellation_requested_at': now, 'updated_at': now,
            }))
        self._event('AGENT_TASK_CANCEL_REQUESTED', 'cancel_agent_task', actor, updated)
        return updated

    def retry(
        self, task_id: str, *, instruction: str, actor: str,
    ) -> AgentTask:
        original = self.registry.load_task(task_id)
        if original.status not in {
            AgentTaskStatus.FAILED, AgentTaskStatus.REJECTED,
            AgentTaskStatus.BLOCKED, AgentTaskStatus.CANCELLED,
        }:
            raise ValueError('retry is allowed only after failure, rejection, blockage, or cancellation')
        if not instruction.strip():
            raise ValueError('retry requires an explicit author instruction')
        return self.create_task(
            task_type=original.task_type, purpose=original.purpose, created_by=actor,
            related_comment_ids=original.related_comment_ids,
            related_action_ids=original.related_action_ids,
            source_element_ids=original.source_element_ids,
            context_policy=original.context_policy, priority=original.priority,
            retry_of_task_id=original.task_id, retry_instruction=instruction.strip(),
        )

    def decide_output(
        self, task_id: str, decision: AgentAuthorDecision | str, *, actor: str,
    ) -> AgentRun:
        actor = actor.strip()
        if not actor:
            raise ValueError('a named author is required for an output decision')
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.AUTHOR_REVIEW or not task.active_run_id:
            raise ValueError('output decision requires a validated AUTHOR_REVIEW task')
        run = self.registry.load_run(task.active_run_id)
        if not run.validation_passed:
            raise ValueError('invalid output cannot be approved for import')
        choice = AgentAuthorDecision(decision)
        now = datetime.now(UTC)
        run_status = (
            AgentRunStatus.APPROVED
            if choice is AgentAuthorDecision.APPROVE_IMPORT else AgentRunStatus.REJECTED
        )
        task_status = (
            AgentTaskStatus.APPROVED
            if choice is AgentAuthorDecision.APPROVE_IMPORT else AgentTaskStatus.REJECTED
        )
        updated_run = run.model_copy(update={
            'status': run_status, 'updated_at': now, 'author_decision': choice,
            'author_decision_by': actor, 'author_decision_at': now,
        })
        updated_task = task.model_copy(update={'status': task_status, 'updated_at': now})
        self.registry.save_run(updated_run)
        self.registry.save_task(updated_task)
        self.registry.write_run_json(run.run_id, 'author_decision.json', {
            'decision': choice.value, 'decision_maker': actor,
            'decision_timestamp': now.isoformat(), 'approval_inferred': False,
        })
        self._event('AGENT_OUTPUT_DECISION', choice.value.lower(), actor, updated_task, {
            'run_id': run.run_id, 'decision': choice.value,
        })
        return updated_run

    def mark_imported(self, task_id: str, *, actor: str) -> AgentRun:
        actor = actor.strip()
        if not actor:
            raise ValueError('a named author is required to import agent output')
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.APPROVED or not task.active_run_id:
            raise PermissionError('import requires explicit APPROVE_IMPORT')
        run = self.registry.load_run(task.active_run_id)
        if run.author_decision is not AgentAuthorDecision.APPROVE_IMPORT:
            raise PermissionError('author import approval is missing')
        now = datetime.now(UTC)
        updated_run = run.model_copy(update={'status': AgentRunStatus.IMPORTED, 'updated_at': now})
        updated_task = task.model_copy(update={'status': AgentTaskStatus.IMPORTED, 'updated_at': now})
        self.registry.save_run(updated_run)
        self.registry.save_task(updated_task)
        self._event('AGENT_OUTPUT_IMPORTED', 'import_agent_output', actor, updated_task, {
            'run_id': run.run_id,
        })
        return updated_run

    def _event(
        self, event_type: str, action: str, actor: str, task: AgentTask,
        extra: dict[str, Any] | None = None,
    ) -> None:
        details = {'task_id': task.task_id, 'task_type': task.task_type.value,
                   'task_status': task.status.value}
        details.update(extra or {})
        self.state.record_event(
            event_type=event_type, action=action, actor=actor, details=details,
        )
