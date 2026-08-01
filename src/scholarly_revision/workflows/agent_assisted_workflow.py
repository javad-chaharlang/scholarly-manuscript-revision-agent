'''Import only validated, explicitly approved Agent output through governed workflows.'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from scholarly_revision.models.agent_run import AgentAuthorDecision, AgentRunStatus
from scholarly_revision.models.agent_task import AgentTaskStatus, AgentTaskType
from scholarly_revision.models.enums import ApprovalState
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.services.agent_run_registry import AgentRunRegistry
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.orchestrator_service import OrchestratorService
from scholarly_revision.services.project_state_service import ProjectStateService

@dataclass(frozen=True, slots=True)
class AgentImportResult:
    task_id: str
    task_type: str
    imported: bool
    staged: bool
    record_count: int
    message: str

class AgentAssistedWorkflow:
    def __init__(self, project_root: str | Path, orchestrator: OrchestratorService | None = None) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.registry = AgentRunRegistry(self.root)
        self.tasks = AgentTaskService(self.root)
        self.orchestrator = orchestrator or OrchestratorService()
        self.state = ProjectStateService(self.root)

    def import_approved_output(self, task_id: str, *, actor: str) -> AgentImportResult:
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.APPROVED or not task.active_run_id:
            raise PermissionError('Agent output requires explicit APPROVE_IMPORT before import')
        run = self.registry.load_run(task.active_run_id)
        if (
            run.status is not AgentRunStatus.APPROVED
            or run.author_decision is not AgentAuthorDecision.APPROVE_IMPORT
            or not run.validation_passed
        ):
            raise PermissionError('run is not valid and author-approved')
        output = read_json(self.registry.run_dir(run.run_id) / 'validated_output.json')
        handlers = {
            AgentTaskType.COMMENT_INTERPRETATION: self._comments,
            AgentTaskType.GAP_ANALYSIS: self._gap,
            AgentTaskType.REVISION_PLAN_DRAFT: self._plan,
            AgentTaskType.REVISION_TEXT_DRAFT: self._drafts,
            AgentTaskType.REFERENCE_NEED_ANALYSIS: self._notes,
            AgentTaskType.SEMANTIC_QA_REVIEW: self._semantic_qa,
            AgentTaskType.RESPONSE_LETTER_DRAFT: self._responses,
            AgentTaskType.GENERAL_RESEARCH_NOTE: self._notes,
        }
        staged, count, message = handlers[task.task_type](task, output, actor)
        self.tasks.mark_imported(task_id, actor=actor)
        return AgentImportResult(
            task_id=task_id, task_type=task.task_type.value, imported=True,
            staged=staged, record_count=count, message=message,
        )

    def _comments(self, task, output, actor):
        path = self.root / 'working' / 'reviewer_comments.json'
        existing = [ReviewerComment.model_validate(item) for item in read_json(path)]
        incoming = {
            item.comment_id: item
            for item in (
                ReviewerComment.model_validate(raw) for raw in output['interpretations']
            )
        }
        fields = {
            'normalized_comment', 'categories', 'priority', 'interpretation',
            'required_actions', 'target_sections', 'shared_with', 'manual_review_required',
        }
        merged = []
        for current in existing:
            candidate = incoming.get(current.comment_id)
            if candidate is None:
                merged.append(current)
                continue
            updates = {name: getattr(candidate, name) for name in fields}
            merged.append(current.model_copy(update=updates))
        write_json(path, [item.model_dump(mode='json') for item in merged])
        self._event('AGENT_INTERPRETATIONS_IMPORTED', actor, task, len(incoming))
        return False, len(incoming), 'Approved interpretations imported; manuscript unchanged.'

    def _gap(self, task, output, actor):
        path = self.root / 'working' / 'agent_gap_analysis_staging.json'
        current = read_json(path) if path.is_file() else {'assessments': []}
        merged = {item['comment_id']: item for item in current['assessments']}
        merged.update({item['comment_id']: item for item in output['assessments']})
        payload = {'schema_version': 1, 'assessments': list(merged.values())}
        write_json(path, payload)
        all_comments = {
            item['comment_id'] for item in read_json(
                self.root / 'working' / 'reviewer_comments.json'
            )
        }
        complete = set(merged) == all_comments
        if complete:
            self.orchestrator.import_gap_analysis(self.root, path, actor=actor)
        self._event('AGENT_GAP_OUTPUT_IMPORTED', actor, task, len(output['assessments']))
        return not complete, len(output['assessments']), (
            'All comments covered; governed gap import completed.'
            if complete else 'Approved records staged; remaining comments are still required.'
        )

    def _plan(self, task, output, actor):
        path = self.root / 'working' / 'revision_plan.json'
        plan = read_json(path) if path.is_file() else {
            'schema_version': 1, 'actions': [], 'approval_gate_status': 'READY_FOR_REVIEW',
        }
        existing = {
            item.action_id: item
            for item in (RevisionAction.model_validate(raw) for raw in plan.get('actions', []))
        }
        for raw in output['actions']:
            item = RevisionAction.model_validate(raw)
            prior = existing.get(item.action_id)
            if prior and prior.approval_state is not ApprovalState.PENDING:
                raise ValueError(f'cannot replace decided revision action: {item.action_id}')
            existing[item.action_id] = item
        plan['actions'] = [item.model_dump(mode='json') for item in existing.values()]
        plan['approval_gate_status'] = 'READY_FOR_REVIEW'
        plan['approval_inferred'] = False
        write_json(path, plan)
        self._event('AGENT_PLAN_DRAFT_IMPORTED', actor, task, len(output['actions']))
        return False, len(output['actions']), 'Draft actions imported as PENDING; Gate 1 remains open.'

    def _drafts(self, task, output, actor):
        template_path = self.root / 'working' / 'revision_draft_template.json'
        if not template_path.is_file():
            raise FileNotFoundError('prepare governed revision drafts before Agent drafting')
        template = read_json(template_path)
        template_by_action = {
            item['action_id']: item for item in template.get('drafts', [])
            if isinstance(item, dict) and item.get('action_id')
        }
        stage_path = self.root / 'working' / 'agent_revision_draft_staging.json'
        staged = read_json(stage_path) if stage_path.is_file() else {'drafts': []}
        merged = {
            item['action_id']: item for item in staged.get('drafts', [])
            if isinstance(item, dict) and item.get('action_id')
        }
        for draft in output['drafts']:
            action_id = draft['action_id']
            base = template_by_action.get(action_id)
            if base is None:
                raise ValueError(f'Agent draft is not in the prepared template: {action_id}')
            if draft['draft_id'] != base['draft']['draft_id']:
                raise ValueError(f'Agent draft changed prepared draft ID: {action_id}')
            merged[action_id] = {
                'action_id': action_id,
                'exact_reviewer_comments': base['exact_reviewer_comments'],
                'approved_action_text': base['approved_action_text'],
                'draft': draft,
            }
        package = {
            'schema_version': 1, 'source_document_hash': template['source_document_hash'],
            'drafts': list(merged.values()), 'approval_inferred': False,
        }
        write_json(stage_path, package)
        complete = set(merged) == set(template_by_action)
        if complete:
            self.orchestrator.import_revision_drafts(self.root, stage_path, actor=actor)
        self._event('AGENT_REVISION_TEXT_IMPORTED', actor, task, len(output['drafts']))
        return not complete, len(output['drafts']), (
            'All prepared drafts imported for explicit Gate 2 decisions.'
            if complete else 'Approved draft staged; remaining prepared drafts are required.'
        )

    def _responses(self, task, output, actor):
        path = self.root / 'working' / 'agent_response_staging.json'
        current = read_json(path) if path.is_file() else {'entries': []}
        merged = {item['comment_id']: item for item in current['entries']}
        merged.update({item['comment_id']: item for item in output['entries']})
        payload = {'schema_version': 1, 'entries': list(merged.values())}
        write_json(path, payload)
        expected = {
            item['comment_id'] for item in read_json(
                self.root / 'working' / 'reviewer_comments.json'
            )
        }
        complete = set(merged) == expected
        if complete:
            self.orchestrator.generate_response(self.root, path, actor=actor)
        self._event('AGENT_RESPONSE_DRAFT_IMPORTED', actor, task, len(output['entries']))
        return not complete, len(output['entries']), (
            'Complete approved response draft sent through governed generation.'
            if complete else 'Approved response entries staged; every comment must be represented.'
        )

    def _semantic_qa(self, task, output, actor):
        path = self.root / 'audit' / 'semantic_qa_findings.json'
        current = read_json(path) if path.is_file() else {
            'lane': 'OPTIONAL_SEMANTIC', 'deterministic_qa_replaced': False, 'findings': [],
        }
        current['findings'].extend(output['findings'])
        write_json(path, current)
        self._event('AGENT_SEMANTIC_QA_IMPORTED', actor, task, len(output['findings']))
        return False, len(output['findings']), 'Semantic findings recorded separately from deterministic QA.'

    def _notes(self, task, output, actor):
        key = 'reference_needs' if 'reference_needs' in output else 'notes'
        path = self.root / 'working' / 'agent_research_notes.json'
        current = read_json(path) if path.is_file() else {'reference_needs': [], 'notes': []}
        current[key].extend(output[key])
        write_json(path, current)
        self._event('AGENT_RESEARCH_OUTPUT_IMPORTED', actor, task, len(output[key]))
        return False, len(output[key]), 'Approved research notes imported; no manuscript text changed.'

    def _event(self, event_type, actor, task, count):
        self.state.record_event(
            event_type=event_type, action='import_approved_agent_output', actor=actor,
            details={'task_id': task.task_id, 'task_type': task.task_type.value,
                     'record_count': count},
        )
