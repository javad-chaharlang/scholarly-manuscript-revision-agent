'''Persistent semantic task workspace with two explicit human gates.'''
from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
import streamlit as st
from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_run import AgentAuthorDecision, AgentRunStatus
from scholarly_revision.models.agent_task import (
    AgentTaskStatus, AgentTaskType, TransmissionDecision,
)
from scholarly_revision.services.agent_run_registry import AgentRunRegistry
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.services.agent_worker_service import AgentWorkerService
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.real_project_checklist_service import (
    RealProjectChecklistService,
)
from scholarly_revision.ui.components import page_title
from scholarly_revision.ui.state import redact_exception
from scholarly_revision.workflows.agent_assisted_workflow import AgentAssistedWorkflow

_ACTIVE = {
    AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING, AgentTaskStatus.COMPLETED_RAW,
    AgentTaskStatus.VALIDATING,
}

def _safe_list(path: Path, key: str | None = None) -> list[dict]:
    if not path.is_file():
        return []
    payload = read_json(path)
    if key:
        payload = payload.get(key, []) if isinstance(payload, dict) else []
    return payload if isinstance(payload, list) else []

def _project_options(root: Path):
    comments = _safe_list(root / 'working' / 'reviewer_comments.json')
    plan = read_json(root / 'working' / 'revision_plan.json') if (
        root / 'working' / 'revision_plan.json'
    ).is_file() else {'actions': []}
    structure = read_json(root / 'working' / 'manuscript_structure.json') if (
        root / 'working' / 'manuscript_structure.json'
    ).is_file() else {'elements': []}
    return (
        [str(item.get('comment_id')) for item in comments if item.get('comment_id')],
        [str(item.get('action_id')) for item in plan.get('actions', []) if item.get('action_id')],
        [
            str(item.get('paragraph_id') or item.get('element_id'))
            for item in structure.get('elements', [])
            if item.get('paragraph_id') or item.get('element_id')
        ],
    )

def _zip_run(directory: Path) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.iterdir()):
            if path.is_file():
                archive.write(path, path.name)
    return stream.getvalue()

def _status_state(status: AgentTaskStatus) -> str:
    if status in {AgentTaskStatus.FAILED, AgentTaskStatus.BLOCKED}:
        return 'error'
    if status in _ACTIVE:
        return 'running'
    return 'complete'

def _task_summary(task, run, context) -> dict:
    duration = run.duration_seconds if run else None
    return {
        'task ID': task.task_id, 'task type': task.task_type.value,
        'related comments': ', '.join(task.related_comment_ids) or 'None',
        'status': task.status.value,
        'progress': f'{run.progress_percent}%' if run else '0%',
        'context size': context.total_character_count if context else None,
        'prompt version': run.prompt_version if run else None,
        'started time': run.started_at.isoformat() if run and run.started_at else None,
        'duration seconds': duration, 'exit code': run.exit_code if run else None,
        'validation result': run.validation_passed if run else None,
        'author decision': run.author_decision.value if run and run.author_decision else None,
    }

def render(orchestrator, project_root, actor) -> None:
    page_title(
        'Agent Tasks',
        'Codex CLI tasks with minimized context, explicit transmission approval, '
        'strict validation, and separate author import approval.',
    )
    root = Path(project_root)
    service = AgentTaskService(root)
    registry = service.registry
    settings = service.settings
    registry.recover_interrupted(stale_seconds=settings.abandoned_run_seconds)
    with st.container(horizontal=True):
        st.badge('Local storage', icon=':material/save:', color='green')
        st.badge(
            'AI transmission requires approval',
            icon=':material/privacy_tip:', color='orange',
        )
        st.badge(
            'Pilot Mode on' if settings.pilot_mode else 'Pilot Mode off',
            icon=':material/science:', color='blue',
        )
    st.warning(
        'Codex receives only the exact context package shown below. '
        'Do not approve transmission until its contents and exclusions are correct.',
        icon=':material/warning:',
    )
    comment_ids, action_ids, element_ids = _project_options(root)
    with st.form('create_agent_task', border=True):
        task_type = st.selectbox(
            'Task type', [item.value for item in AgentTaskType],
            key='agent_create_type',
        )
        purpose = st.text_area(
            'Purpose', placeholder='State the bounded scholarly task.',
            key='agent_create_purpose',
        )
        selected_comments = st.multiselect(
            'Related reviewer comments', comment_ids, key='agent_create_comments',
        )
        selected_actions = st.multiselect(
            'Related revision actions', action_ids, key='agent_create_actions',
        )
        selected_elements = st.multiselect(
            'Source paragraph or element IDs', element_ids, key='agent_create_elements',
        )
        policy = st.selectbox(
            'Context policy', [item.value for item in ContextPolicy],
            key='agent_create_policy',
        )
        created = st.form_submit_button(
            'Create task', icon=':material/add_task:',
            disabled=not bool(actor.strip()) or not settings.allow_semantic_tasks,
        )
    if created:
        try:
            task = service.create_task(
                task_type=task_type, purpose=purpose, created_by=actor,
                related_comment_ids=selected_comments,
                related_action_ids=selected_actions,
                source_element_ids=selected_elements, context_policy=policy,
            )
            st.success(f'Created {task.task_id}.')
        except Exception as exc:
            st.error(redact_exception(exc))
    tasks = registry.tasks()
    if not tasks:
        st.info('No Agent tasks exist for this project.')
        return
    st.subheader('Task registry')
    st.dataframe(
        [{
            'task_id': item.task_id, 'task_type': item.task_type.value,
            'related_comments': item.related_comment_ids, 'status': item.status.value,
            'updated_at': item.updated_at,
        } for item in tasks],
        key='agent_task_registry',
    )
    task_labels = {
        f'{item.task_id} | {item.task_type.value} | {item.status.value}': item.task_id
        for item in tasks
    }
    selected_label = st.selectbox(
        'Selected task', list(task_labels),
        key='agent_selected_task', persist_state='session',
    )
    selected_id = task_labels[selected_label]

    @st.fragment(run_every='2s')
    def task_panel(task_id: str) -> None:
        local_service = AgentTaskService(root)
        local_registry = local_service.registry
        local_registry.recover_interrupted(
            stale_seconds=local_service.settings.abandoned_run_seconds,
        )
        task = local_registry.load_task(task_id)
        context = None
        try:
            context = local_registry.load_context(task_id)
        except FileNotFoundError:
            pass
        run = (
            local_registry.load_run(task.active_run_id)
            if task.active_run_id else None
        )
        with st.status(
            f'{task.task_type.value} · {task.status.value}',
            state=_status_state(task.status), expanded=task.status in _ACTIVE,
        ):
            st.json(_task_summary(task, run, context), expanded=True)
        if task.last_error_code:
            detail = task.last_error_message or 'No details supplied.'
            st.error(f'{task.last_error_code}: {detail}')
            st.caption(
                'Recovery: inspect raw output and audit metadata, then cancel or use '
                'Retry with Instruction. Interrupted runs never resume automatically.'
            )
        with st.container(horizontal=True):
            if st.button(
                'Prepare Context', icon=':material/package_2:',
                disabled=task.status not in {
                    AgentTaskStatus.CREATED,
                    AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
                    AgentTaskStatus.CONTEXT_READY,
                },
                key=f'prepare_{task_id}',
            ):
                try:
                    local_service.prepare_context(task_id)
                    st.rerun(scope='fragment')
                except Exception as exc:
                    st.error(redact_exception(exc))
            if st.button(
                'Cancel', icon=':material/cancel:',
                disabled=task.status in {
                    AgentTaskStatus.IMPORTED, AgentTaskStatus.REJECTED,
                    AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED,
                },
                key=f'cancel_{task_id}',
            ):
                try:
                    local_service.cancel(task_id, actor=actor)
                    st.rerun(scope='fragment')
                except Exception as exc:
                    st.error(redact_exception(exc))
        if st.button(
            'Review Context', icon=':material/visibility:',
            disabled=context is None, key=f'review_context_{task_id}',
        ):
            st.session_state[f'show_context_{task_id}'] = True
        if context is not None and st.session_state.get(f'show_context_{task_id}', False):
            st.subheader('Review Context')
            st.caption(
                f'Policy: {context.context_policy.value} · '
                f'{context.total_character_count:,} characters · '
                f'{len(context.input_file_hashes)} hashed input files'
            )
            if (
                context.total_character_count
                > local_service.settings.context_warning_characters
            ):
                st.warning(
                    'This package exceeds the configured context-size warning '
                    'threshold. Modify the context before approval if possible.'
                )
            st.json({
                'reviewer comments included': [
                    item.model_dump(mode='json')
                    for item in context.reviewer_comments_included
                ],
                'manuscript sections included': [
                    item.model_dump(mode='json')
                    for item in context.manuscript_sections_included
                ],
                'paragraph IDs included': context.paragraph_ids_included,
                'evidence records included': context.evidence_records_included,
                'result records included': context.result_records_included,
                'references included': context.references_included,
                'exclusions': context.exclusions, 'redactions': context.redactions,
                'input file hashes': context.input_file_hashes,
                'exact transmitted payload': context.transmitted_payload,
            }, expanded=False)
            confirmed = st.checkbox(
                'I reviewed the exact context and approve transmitting it to Codex.',
                key=f'confirm_transmission_{task_id}',
                disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            )
            revised_comments = st.multiselect(
                'Modify reviewer-comment scope', comment_ids,
                default=task.related_comment_ids,
                key=f'modify_comments_{task_id}',
                disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            )
            revised_actions = st.multiselect(
                'Modify action scope', action_ids, default=task.related_action_ids,
                key=f'modify_actions_{task_id}',
                disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            )
            revised_elements = st.multiselect(
                'Modify paragraph or element scope', element_ids,
                default=task.source_element_ids,
                key=f'modify_elements_{task_id}',
                disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            )
            revised_policy = st.selectbox(
                'Modify context policy', [item.value for item in ContextPolicy],
                index=[item.value for item in ContextPolicy].index(task.context_policy),
                key=f'modify_policy_{task_id}',
                disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
            )
            with st.container(horizontal=True):
                if st.button(
                    'Approve Transmission', icon=':material/verified_user:',
                    disabled=(
                        task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL
                        or not confirmed or not actor.strip()
                    ),
                    key=f'approve_transmission_{task_id}',
                ):
                    try:
                        local_service.transmission_decision(
                            task_id, TransmissionDecision.APPROVE_TRANSMISSION,
                            actor=actor,
                        )
                        st.rerun(scope='fragment')
                    except Exception as exc:
                        st.error(redact_exception(exc))
                if st.button(
                    'Modify Context', icon=':material/edit:',
                    disabled=task.status is not AgentTaskStatus.WAITING_FOR_TRANSMISSION_APPROVAL,
                    key=f'modify_context_{task_id}',
                ):
                    try:
                        local_service.modify_context_scope(
                            task_id, actor=actor,
                            related_comment_ids=revised_comments,
                            related_action_ids=revised_actions,
                            source_element_ids=revised_elements,
                            context_policy=revised_policy,
                        )
                        st.rerun(scope='fragment')
                    except Exception as exc:
                        st.error(redact_exception(exc))
        if st.button(
            'Run with Codex', icon=':material/play_arrow:', type='primary',
            disabled=task.status is not AgentTaskStatus.CONTEXT_READY,
            key=f'run_codex_{task_id}',
        ):
            try:
                local_service.queue(task_id, actor=actor)
                AgentWorkerService(root).start_background(task_id)
                st.rerun(scope='fragment')
            except Exception as exc:
                st.error(redact_exception(exc))
        if run is not None:
            run_dir = local_registry.run_dir(run.run_id)
            raw_stdout = run_dir / 'raw_stdout.txt'
            validated = run_dir / 'validated_output.json'
            with st.container(horizontal=True):
                if raw_stdout.is_file():
                    st.download_button(
                        'View Raw Output', raw_stdout.read_bytes(),
                        file_name='raw_stdout.txt', mime='text/plain',
                        icon=':material/raw_on:', key=f'raw_{task_id}',
                    )
                if validated.is_file():
                    st.download_button(
                        'View Validated Output', validated.read_bytes(),
                        file_name='validated_output.json', mime='application/json',
                        icon=':material/data_object:', key=f'validated_{task_id}',
                    )
                st.download_button(
                    'Export Package', _zip_run(run_dir),
                    file_name=f'{run.run_id}-audit.zip', mime='application/zip',
                    icon=':material/archive:', key=f'export_{task_id}',
                )
            with st.container(horizontal=True):
                if st.button(
                    'Approve Import', icon=':material/check_circle:',
                    disabled=(
                        task.status is not AgentTaskStatus.AUTHOR_REVIEW
                        or not actor.strip()
                    ),
                    key=f'approve_import_{task_id}',
                ):
                    try:
                        local_service.decide_output(
                            task_id, AgentAuthorDecision.APPROVE_IMPORT, actor=actor,
                        )
                        st.rerun(scope='fragment')
                    except Exception as exc:
                        st.error(redact_exception(exc))
                if st.button(
                    'Reject Output', icon=':material/block:',
                    disabled=task.status is not AgentTaskStatus.AUTHOR_REVIEW,
                    key=f'reject_output_{task_id}',
                ):
                    local_service.decide_output(
                        task_id, AgentAuthorDecision.REJECT_OUTPUT, actor=actor,
                    )
                    st.rerun(scope='fragment')
                if st.button(
                    'Import approved output', icon=':material/download_done:',
                    disabled=task.status is not AgentTaskStatus.APPROVED,
                    key=f'import_output_{task_id}',
                ):
                    try:
                        result = AgentAssistedWorkflow(
                            root, orchestrator,
                        ).import_approved_output(task_id, actor=actor)
                        st.success(result.message)
                        st.rerun(scope='fragment')
                    except Exception as exc:
                        st.error(redact_exception(exc))
        retry_instruction = st.text_area(
            'Retry with Instruction', key=f'retry_instruction_{task_id}',
            disabled=task.status not in {
                AgentTaskStatus.FAILED, AgentTaskStatus.REJECTED,
                AgentTaskStatus.BLOCKED, AgentTaskStatus.CANCELLED,
            },
        )
        if st.button(
            'Retry with Instruction', icon=':material/replay:',
            disabled=(
                task.status not in {
                    AgentTaskStatus.FAILED, AgentTaskStatus.REJECTED,
                    AgentTaskStatus.BLOCKED, AgentTaskStatus.CANCELLED,
                } or not retry_instruction.strip()
            ),
            key=f'retry_{task_id}',
        ):
            try:
                retried = local_service.retry(
                    task_id, instruction=retry_instruction, actor=actor,
                )
                st.success(f'Created {retried.task_id}; transmission approval is required again.')
            except Exception as exc:
                st.error(redact_exception(exc))

    task_panel(selected_id)

    st.subheader('Real-project checklist', anchor=False)
    checklist_service = RealProjectChecklistService(root)
    checklist = checklist_service.evaluate()
    st.dataframe(checklist['items'], hide_index=True, width='stretch')
    if service.settings.pilot_mode:
        st.warning(
            'Pilot Mode is ON. Batch execution is disabled, every semantic task '
            'requires both human gates, and release remains blocked until these '
            'checks are explicitly approved.'
        )
        pilot_path = root / 'audit' / 'pilot_checks.json'
        if pilot_path.is_file():
            st.success('Pilot checks have a recorded explicit approval.')
        with st.expander('Pilot release checks', expanded=False):
            pilot_labels = {
                'context_minimization_reviewed': 'Context minimization reviewed',
                'transmission_gate_verified': 'Transmission gate verified',
                'import_gate_verified': 'Import gate verified',
                'additional_backups_verified': 'Additional backups verified',
                'complex_word_objects_reviewed': 'Complex Word objects reviewed manually',
                'cross_document_consistency_verified': 'Cross-document consistency verified',
            }
            pilot_checks = {
                key: st.checkbox(label, key=f'pilot_{key}')
                for key, label in pilot_labels.items()
            }
            pilot_note = st.text_area('Pilot approval note', key='pilot_approval_note')
            if st.button(
                'Approve all Pilot Mode checks',
                disabled=not actor.strip() or not all(pilot_checks.values()),
                icon=':material/fact_check:',
            ):
                try:
                    checklist_service.record_pilot_approval(
                        actor=actor, checks=pilot_checks, note=pilot_note,
                    )
                    st.success('Pilot approval recorded in the audit timeline.')
                    st.rerun()
                except Exception as exc:
                    st.error(redact_exception(exc))
