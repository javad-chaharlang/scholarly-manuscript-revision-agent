'''Unified local facade over the existing deterministic revision workflows.'''

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.enums import (
    ApprovalDecision, ResultStatus, RevisionTextDecision,
)
from scholarly_revision.models.project import InputFiles
from scholarly_revision.models.project_state import ProjectState, ProjectStateRecord
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.revision_draft import (
    RevisionDraft, RevisionTextDecisionRecord,
)
from scholarly_revision.services.approval_service import approval_gate_status, record_decision
from scholarly_revision.services.config_loader import load_project_manifest, save_project_manifest
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.manual_visual_qa_service import (
    import_manual_visual_qa_decisions, prepare_manual_visual_qa_template,
)
from scholarly_revision.services.project_registry import ProjectRegistry
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.services.project_workspace import copy_input_file, sha256_file
from scholarly_revision.services.qa_report_service import apply_qa_decisions, verify_qa_resolutions
from scholarly_revision.services.response_letter_service import load_response_sources
from scholarly_revision.services.revision_drafting_service import load_project_revision_sources
from scholarly_revision.services.revision_text_approval_service import (
    record_revision_text_decision,
)
from scholarly_revision.services.scientific_qa_service import load_qa_config
from scholarly_revision.tools.docx_reader import read_docx
from scholarly_revision.tools.workbook_builder import (
    update_revision_execution_workbook, update_revision_workbook,
)
from scholarly_revision.workflows.finalization_workflow import (
    build_submission_package, generate_response_letter,
    prepare_response_drafts, run_final_consistency_check, verify_response_letter,
)
from scholarly_revision.workflows.gap_analysis_workflow import (
    import_and_plan, prepare_gap_analysis,
)
from scholarly_revision.workflows.intake_workflow import IntakeRequest, run_intake_workflow
from scholarly_revision.workflows.revision_execution_workflow import (
    apply_approved_revisions, import_completed_revision_drafts,
    import_completed_text_decisions, prepare_revision_drafts,
    verify_revision_outputs,
)
from scholarly_revision.workflows.scientific_qa_workflow import run_scientific_qa_workflow


@dataclass(frozen=True, slots=True)
class NewProjectRequest:
    workspace_root: Path
    project_name: str
    manuscript_id: str
    manuscript_title: str
    journal: str
    revision_round: int
    reviewer_count: int
    manuscript_language: str
    response_language: str
    citation_style: str
    result_status: ResultStatus | str
    reviewer_file: Path
    manuscript_file: Path
    editor_letter: Path | None = None
    result_registry: Path | None = None
    reference_registry: Path | None = None
    response_sample: Path | None = None
    previous_manuscript: Path | None = None
    journal_template: Path | None = None


ACTION_STATES: dict[str, set[ProjectState]] = {
    'complete_intake_review': {ProjectState.INTAKE_REVIEW},
    'prepare_gap_analysis': {ProjectState.GAP_ANALYSIS_PENDING},
    'import_gap_analysis': {ProjectState.GAP_ANALYSIS_PENDING},
    'record_plan_decision': {ProjectState.PLAN_APPROVAL, ProjectState.BLOCKED},
    'prepare_revision_drafts': {ProjectState.REVISION_DRAFTING},
    'import_revision_drafts': {ProjectState.REVISION_DRAFTING},
    'import_text_decisions': {ProjectState.TEXT_APPROVAL},
    'apply_revisions': {ProjectState.REVISION_APPLICATION},
    'run_scientific_qa': {ProjectState.SCIENTIFIC_QA},
    'import_qa_decisions': {ProjectState.SCIENTIFIC_QA, ProjectState.BLOCKED},
    'prepare_response': {ProjectState.RESPONSE_PREPARATION},
    'generate_response': {ProjectState.RESPONSE_PREPARATION},
    'verify_response': {ProjectState.RESPONSE_PREPARATION},
    'prepare_visual_qa': {ProjectState.VISUAL_QA},
    'record_visual_qa': {ProjectState.VISUAL_QA, ProjectState.BLOCKED},
    'final_release': {ProjectState.READY_FOR_RELEASE},
}


def _validate_json_file(path: Path, label: str) -> None:
    if path.suffix.lower() != '.json':
        raise ValueError(f'{label} must be a JSON file')
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'{label} is not readable JSON') from exc
    if not isinstance(payload, (dict, list)):
        raise ValueError(f'{label} must contain a JSON object or list')


class OrchestratorService:
    '''State-aware application service; no scientific prose is generated here.'''

    def __init__(self, workspace_root: str | Path) -> None:
        self.registry = ProjectRegistry(workspace_root)

    def _services(self, project_root: str | Path) -> tuple[Path, ProjectStateService]:
        root = Path(project_root).expanduser().resolve()
        return root, ProjectStateService(root)

    def _sync(self, state: ProjectStateRecord) -> ProjectStateRecord:
        self.registry.update_state(state.project_id, state.state)
        return state

    def _require(self, project_root: str | Path, action: str) -> tuple[Path, ProjectStateService]:
        root, states = self._services(project_root)
        current = states.load()
        allowed = ACTION_STATES.get(action, set())
        if current.state not in allowed:
            raise ValueError(
                f'action {action} is invalid while project state is {current.state.value}'
            )
        if current.state is ProjectState.BLOCKED:
            required_prior = {
                'record_plan_decision': ProjectState.PLAN_APPROVAL,
                'import_qa_decisions': ProjectState.SCIENTIFIC_QA,
                'record_visual_qa': ProjectState.VISUAL_QA,
            }.get(action)
            if required_prior is None or current.blocked_from is not required_prior:
                raise ValueError(
                    f'action {action} cannot resolve blockers from '
                    f'{current.blocked_from.value if current.blocked_from else UNKNOWN}'
                )
        return root, states

    @staticmethod
    def validate_new_project(request: NewProjectRequest) -> None:
        if request.revision_round < 1 or request.reviewer_count < 1:
            raise ValueError('revision round and reviewer count must be positive')
        required_text = {
            'project name': request.project_name,
            'manuscript ID': request.manuscript_id,
            'manuscript title': request.manuscript_title,
            'journal': request.journal,
            'manuscript language': request.manuscript_language,
            'response language': request.response_language,
            'citation style': request.citation_style,
        }
        for label, value in required_text.items():
            if not value.strip():
                raise ValueError(f'{label} must not be blank')
        for label, path in (
            ('reviewer file', request.reviewer_file),
            ('manuscript file', request.manuscript_file),
            ('editor letter', request.editor_letter),
            ('response sample', request.response_sample),
            ('previous manuscript', request.previous_manuscript),
            ('journal template', request.journal_template),
        ):
            if path is None:
                continue
            if path.suffix.lower() != '.docx':
                raise ValueError(f'{label} must be DOCX')
            read_docx(path)
        for label, path in (
            ('result registry', request.result_registry),
            ('reference registry', request.reference_registry),
        ):
            if path is not None:
                _validate_json_file(path, label)

    def create_project(
        self, request: NewProjectRequest, *, actor: str,
    ) -> ProjectStateRecord:
        self.validate_new_project(request)
        result = run_intake_workflow(IntakeRequest(
            workspace_root=request.workspace_root,
            project_name=request.project_name,
            manuscript_id=request.manuscript_id,
            reviewer_file=request.reviewer_file,
            manuscript_file=request.manuscript_file,
            journal=request.journal,
            reviewer_count=request.reviewer_count,
            force=False,
        ))
        root = result.workspace.root
        optional: dict[str, str | None] = {
            'editor_letter': None, 'result_registry': None,
            'reference_registry': None, 'response_sample': None,
            'previous_manuscript': None, 'journal_template': None,
        }
        for role, source in (
            ('editor_letter', request.editor_letter),
            ('result_registry', request.result_registry),
            ('reference_registry', request.reference_registry),
            ('response_sample', request.response_sample),
            ('previous_manuscript', request.previous_manuscript),
            ('journal_template', request.journal_template),
        ):
            if source is not None:
                optional[role] = copy_input_file(source, result.workspace, role).name
        manifest = load_project_manifest(result.manifest_path)
        manifest = manifest.model_copy(update={
            'manuscript_title': request.manuscript_title.strip(),
            'revision_round': request.revision_round,
            'manuscript_language': request.manuscript_language.strip(),
            'response_language': request.response_language.strip(),
            'citation_style': request.citation_style.strip(),
            'result_status': ResultStatus(request.result_status),
            'input_files': InputFiles(**{
                **manifest.input_files.model_dump(), **optional,
            }),
            'updated_at': datetime.now(UTC),
        })
        save_project_manifest(manifest, result.manifest_path)
        states = ProjectStateService(root)
        state = states.initialize(result.workspace.slug, actor=actor)
        state = states.transition(
            ProjectState.INTAKE_PENDING, action='begin_intake', actor=actor,
        )
        target = (
            ProjectState.INTAKE_REVIEW
            if result.manual_review_count or result.warnings
            else ProjectState.GAP_ANALYSIS_PENDING
        )
        state = states.transition(
            target, action='complete_intake', actor=actor,
            details={
                'comment_count': len(result.extracted_comment_ids),
                'manual_review_count': result.manual_review_count,
                'warning_count': len(result.warnings),
            },
        )
        self.registry.register(root, state.state, project_id=state.project_id)
        return state

    def resume(self, project_id: str) -> ProjectStateRecord:
        entry = self.registry.get(project_id)
        state = ProjectStateService(entry.project_root).load()
        self.registry.update_state(project_id, state.state)
        return state

    def available_actions(self, project_root: str | Path) -> dict[str, bool]:
        root = Path(project_root).expanduser().resolve()
        record = ProjectStateService(root).load()
        state = record.state
        actions = {
            action: state in allowed for action, allowed in ACTION_STATES.items()
        }
        actions['prepare_gap_analysis'] &= not (
            root / 'working' / 'gap_analysis_template.json'
        ).exists()
        actions['prepare_revision_drafts'] &= not (
            root / 'working' / 'revision_draft_template.json'
        ).exists()
        actions['prepare_response'] &= not (
            root / 'working' / 'response_drafting_package.json'
        ).exists()
        actions['generate_response'] &= not (
            root / 'outputs' / 'Response_to_Reviewers.docx'
        ).exists()
        actions['prepare_visual_qa'] &= not (
            root / 'working' / 'manual_visual_qa_decision_template.json'
        ).exists()
        if state is ProjectState.BLOCKED:
            actions['record_plan_decision'] &= (
                record.blocked_from is ProjectState.PLAN_APPROVAL
            )
            actions['import_qa_decisions'] &= (
                record.blocked_from is ProjectState.SCIENTIFIC_QA
            )
            actions['record_visual_qa'] &= (
                record.blocked_from is ProjectState.VISUAL_QA
            )
        return actions

    def complete_intake_review(self, project_root: str | Path, *, actor: str) -> ProjectStateRecord:
        _, states = self._require(project_root, 'complete_intake_review')
        return self._sync(states.transition(
            ProjectState.GAP_ANALYSIS_PENDING,
            action='complete_intake_review', actor=actor,
        ))

    def prepare_gap_analysis(self, project_root: str | Path, *, actor: str) -> Any:
        root, states = self._require(project_root, 'prepare_gap_analysis')
        manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
        if not manifest.input_files.manuscript:
            raise ValueError('project manifest has no manuscript file')
        result = prepare_gap_analysis(root, root / 'input' / manifest.input_files.manuscript)
        states.record_event(
            event_type='GAP_ANALYSIS_PREPARED', action='prepare_gap_analysis', actor=actor,
            details={'comment_count': result.comment_count,
                     'structural_element_count': result.structural_element_count},
        )
        return result

    def import_gap_analysis(
        self, project_root: str | Path, analysis_file: str | Path, *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'import_gap_analysis')
        result = import_and_plan(root, analysis_file)
        state = states.transition(
            ProjectState.PLAN_APPROVAL, action='import_gap_analysis', actor=actor,
            details={'action_count': result.action_count},
        )
        self._sync(state)
        return result

    def record_plan_decision(
        self, project_root: str | Path, *, action_id: str,
        decision: ApprovalDecision | str, decision_maker: str,
        actor: str, author_note: str | None = None,
        modified_action_text: str | None = None,
        evidence_request: str | None = None,
    ) -> ProjectStateRecord:
        root, states = self._require(project_root, 'record_plan_decision')
        if states.load().state is ProjectState.BLOCKED:
            self._sync(states.transition(
                ProjectState.PLAN_APPROVAL,
                action='resume_plan_approval', actor=actor,
            ))
        plan_path = root / 'working' / 'revision_plan.json'
        plan = record_decision(
            read_json(plan_path), action_id=action_id, decision=decision,
            decision_maker=decision_maker, author_note=author_note,
            modified_action_text=modified_action_text,
            evidence_request=evidence_request,
        )
        write_json(plan_path, plan)
        comments = [ReviewerComment.model_validate(item) for item in read_json(
            root / 'working' / 'reviewer_comments.json'
        )]
        imported = read_json(root / 'working' / 'gap_analysis_imported.json')
        from scholarly_revision.models.gap_analysis import GapAnalysisAssessment
        assessments = [GapAnalysisAssessment.model_validate(item) for item in imported['assessments']]
        actions = [RevisionAction.model_validate(item) for item in plan['actions']]
        update_revision_workbook(
            root / 'outputs' / 'Revision_Master.xlsx', comments,
            assessments, actions, str(plan['approval_gate_status']),
        )
        states.record_event(
            event_type='PLAN_DECISION_RECORDED', action='record_plan_decision',
            actor=actor, details={'action_id': action_id,
                                  'decision': ApprovalDecision(decision).value,
                                  'decision_maker': decision_maker},
        )
        gate = approval_gate_status(actions).value
        if gate == 'APPROVED':
            return self._sync(states.transition(
                ProjectState.REVISION_DRAFTING,
                action='complete_plan_approval', actor=actor,
                details={'action_count': len(actions)},
            ))
        if gate == 'BLOCKED':
            return self._sync(states.block(
                ['One or more revision actions require additional evidence.'],
                action='evaluate_plan_approval', actor=actor,
            ))
        return states.load()

    def prepare_revision_drafts(self, project_root: str | Path, *, actor: str) -> Any:
        root, states = self._require(project_root, 'prepare_revision_drafts')
        result = prepare_revision_drafts(root)
        states.record_event(
            event_type='REVISION_DRAFTS_PREPARED', action='prepare_revision_drafts',
            actor=actor, details={'draft_count': result.draft_count,
                                  'blocked_action_count': result.blocked_action_count},
        )
        return result

    def import_revision_drafts(
        self, project_root: str | Path, draft_file: str | Path, *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'import_revision_drafts')
        result = import_completed_revision_drafts(root, draft_file)
        state = states.transition(
            ProjectState.TEXT_APPROVAL, action='import_revision_drafts', actor=actor,
            details={'draft_count': result.draft_count},
        )
        self._sync(state)
        return result

    def import_text_decisions(
        self, project_root: str | Path, decisions_file: str | Path, *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'import_text_decisions')
        result = import_completed_text_decisions(root, decisions_file)
        payload = read_json(result.revision_drafts_path)
        drafts = [RevisionDraft.model_validate(item['draft']) for item in payload['drafts']]
        states.record_event(
            event_type='TEXT_DECISIONS_RECORDED', action='import_text_decisions',
            actor=actor, details={'decision_count': result.decision_count},
        )
        approved = [item for item in drafts if item.approval_state.value == 'APPROVED']
        pending = [item for item in drafts if item.approval_state.value == 'PENDING']
        if approved and not pending:
            self._sync(states.transition(
                ProjectState.REVISION_APPLICATION,
                action='complete_text_approval', actor=actor,
                details={'approved_draft_count': len(approved)},
            ))
        return result

    def record_text_decision(
        self, project_root: str | Path, *, draft_id: str,
        decision: RevisionTextDecision | str, decision_maker: str,
        actor: str, author_modified_text: str | None = None,
        author_note: str | None = None, evidence_request: str | None = None,
        rewrite_instruction: str | None = None,
    ) -> ProjectStateRecord:
        root, states = self._require(project_root, 'import_text_decisions')
        path = root / 'working' / 'revision_drafts.json'
        payload = read_json(path)
        drafts = [
            RevisionDraft.model_validate(item['draft'])
            for item in payload.get('drafts', [])
        ]
        target = next((item for item in drafts if item.draft_id == draft_id), None)
        if target is None:
            raise ValueError(f'unknown draft ID: {draft_id}')
        selected = RevisionTextDecision(decision)
        approved_text = None
        if selected is RevisionTextDecision.APPROVE_TEXT:
            approved_text = target.proposed_text
        elif selected is RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION:
            approved_text = author_modified_text
        record = RevisionTextDecisionRecord(
            draft_id=draft_id, decision=selected,
            decision_maker=decision_maker,
            decision_timestamp=datetime.now(UTC),
            approved_text=approved_text,
            author_modified_text=author_modified_text,
            author_note=author_note,
            evidence_request=evidence_request,
            rewrite_instruction=rewrite_instruction,
        )
        updated = record_revision_text_decision(payload, record)
        write_json(path, updated)
        audit_path = root / 'audit' / 'revision_text_decisions.json'
        audit = read_json(audit_path) if audit_path.is_file() else {
            'schema_version': 1, 'decisions': [],
            'approval_inferred': False,
        }
        audit['decisions'].append(record.model_dump(mode='json'))
        write_json(audit_path, audit)
        comments, actions, _, _ = load_project_revision_sources(root)
        current_drafts = [
            RevisionDraft.model_validate(item['draft'])
            for item in updated['drafts']
        ]
        update_revision_execution_workbook(
            root / 'outputs' / 'Revision_Master.xlsx',
            comments, actions, current_drafts, [],
            output_version=None, document_verification_status='NOT_RUN',
        )
        states.record_event(
            event_type='TEXT_DECISION_RECORDED', action='record_text_decision',
            actor=actor, details={
                'draft_id': draft_id, 'decision': selected.value,
                'decision_maker': decision_maker,
            },
        )
        pending = [item for item in current_drafts if item.author_decision is None]
        approved = [
            item for item in current_drafts
            if item.approval_state.value == 'APPROVED'
        ]
        if not pending and approved:
            return self._sync(states.transition(
                ProjectState.REVISION_APPLICATION,
                action='complete_text_approval', actor=actor,
                details={'approved_draft_count': len(approved)},
            ))
        return states.load()

    def apply_revisions(self, project_root: str | Path, *, actor: str) -> Any:
        root, states = self._require(project_root, 'apply_revisions')
        manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
        if not manifest.input_files.manuscript:
            raise ValueError('project manifest has no manuscript file')
        source = root / 'input' / manifest.input_files.manuscript
        result = apply_approved_revisions(root, source)
        verify_revision_outputs(root, source)
        self._sync(states.transition(
            ProjectState.SCIENTIFIC_QA, action='apply_and_verify_revisions',
            actor=actor, details={'applied_change_count': result.applied_change_count,
                                  'output_version': result.output_version},
        ))
        return result

    def run_scientific_qa(self, project_root: str | Path, *, actor: str) -> Any:
        root, states = self._require(project_root, 'run_scientific_qa')
        manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
        result = run_scientific_qa_workflow(
            project_root=root,
            highlighted_manuscript=root / 'outputs' / 'Revised_Manuscript_Highlighted.docx',
            clean_manuscript=root / 'outputs' / 'Revised_Manuscript_Clean.docx',
            results_registry=(root / 'input' / manifest.input_files.result_registry)
            if manifest.input_files.result_registry else None,
            reference_registry=(root / 'input' / manifest.input_files.reference_registry)
            if manifest.input_files.reference_registry else None,
            config_path=Path(__file__).resolve().parents[3] / 'templates' / 'scientific_qa_config.yaml',
        )
        if result.report.blocker_count:
            state = states.block(
                [f'{result.report.blocker_count} unresolved scientific QA blocker(s)'],
                action='run_scientific_qa', actor=actor,
                details={'blocker_count': result.report.blocker_count},
            )
        else:
            state = states.transition(
                ProjectState.RESPONSE_PREPARATION, action='run_scientific_qa',
                actor=actor, details={'issue_count': result.report.total_issues},
            )
        self._sync(state)
        return result

    def import_qa_decisions(
        self, project_root: str | Path, decision_file: str | Path, *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'import_qa_decisions')
        report = apply_qa_decisions(root, decision_file)
        verified = verify_qa_resolutions(root)
        states.record_event(
            event_type='QA_DECISIONS_RECORDED', action='import_qa_decisions', actor=actor,
            details={'blocker_count': report.blocker_count,
                     'readiness': verified['final_release_readiness']},
        )
        if states.load().state is ProjectState.BLOCKED and not report.blocker_count:
            self._sync(states.transition(
                ProjectState.SCIENTIFIC_QA, action='resume_after_qa_resolution', actor=actor,
            ))
        if states.load().state is ProjectState.SCIENTIFIC_QA and not report.blocker_count:
            self._sync(states.transition(
                ProjectState.RESPONSE_PREPARATION, action='complete_scientific_qa', actor=actor,
            ))
        return report

    def prepare_response(self, project_root: str | Path, *, actor: str) -> Path:
        root, states = self._require(project_root, 'prepare_response')
        path = prepare_response_drafts(root)
        states.record_event(
            event_type='RESPONSE_DRAFT_PREPARED', action='prepare_response', actor=actor,
        )
        return path

    def generate_response(
        self, project_root: str | Path, response_draft: str | Path, *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'generate_response')
        result = generate_response_letter(root, response_draft)
        states.record_event(
            event_type='RESPONSE_LETTER_GENERATED', action='generate_response', actor=actor,
            details={'entry_count': len(result.package.entries)},
        )
        return result

    def verify_response(self, project_root: str | Path, *, actor: str) -> Any:
        root, states = self._require(project_root, 'verify_response')
        result = verify_response_letter(root, root / 'outputs' / 'Response_to_Reviewers.docx')
        if result.passed:
            self._sync(states.transition(
                ProjectState.VISUAL_QA, action='verify_response', actor=actor,
                details={'verified_count': result.verified_count},
            ))
        else:
            states.record_event(
                event_type='RESPONSE_VERIFICATION_FAILED', action='verify_response', actor=actor,
                details={'blocked_count': result.blocked_count},
            )
        return result

    def prepare_visual_qa(self, project_root: str | Path, *, actor: str) -> Path:
        root, states = self._require(project_root, 'prepare_visual_qa')
        path = prepare_manual_visual_qa_template(root)
        states.record_event(
            event_type='VISUAL_QA_TEMPLATE_PREPARED', action='prepare_visual_qa', actor=actor,
        )
        return path

    def record_visual_qa(
        self, project_root: str | Path, decisions: str | Path | dict[str, Any],
        *, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'record_visual_qa')
        if states.load().state is ProjectState.BLOCKED:
            self._sync(states.transition(
                ProjectState.VISUAL_QA,
                action='resume_visual_qa', actor=actor,
            ))
        record = import_manual_visual_qa_decisions(root, decisions)
        states.record_event(
            event_type='VISUAL_QA_DECISIONS_RECORDED', action='record_visual_qa', actor=actor,
            details={'artifact_count': len(record.decisions),
                     'all_approved': record.all_approved},
        )
        result = run_final_consistency_check(root)
        release = read_json(root / 'audit' / 'final_release_report.json')
        failed = [
            item['category'] for item in release.get('checklist', {}).get('checks', [])
            if item.get('required') and not item.get('passed')
            and item.get('category') != 'final human release approval recorded'
        ]
        if record.all_approved and not failed:
            self._sync(states.transition(
                ProjectState.READY_FOR_RELEASE, action='complete_visual_qa', actor=actor,
                details={'pre_release_check_count': len(
                    release.get('checklist', {}).get('checks', [])
                )},
            ))
        elif failed:
            self._sync(states.block(
                failed, action='evaluate_release_readiness', actor=actor,
                details={'failed_check_count': len(failed)},
            ))
        return result

    def final_release(
        self, project_root: str | Path, *, release_name: str,
        decision_maker: str, confirmation: str, actor: str,
    ) -> Any:
        root, states = self._require(project_root, 'final_release')
        state = states.load()
        expected = f'RELEASE {state.project_id}'
        if confirmation != expected:
            raise ValueError(f'final release requires exact confirmation: {expected}')
        artifacts = {}
        for name in (
            'Response_to_Reviewers.docx', 'Revised_Manuscript_Highlighted.docx',
            'Revised_Manuscript_Clean.docx', 'Revision_Master.xlsx',
            'Scientific_QA_Report.xlsx',
        ):
            path = root / 'outputs' / name
            if not path.is_file():
                raise FileNotFoundError(f'required release artifact is missing: {name}')
            artifacts[name] = sha256_file(path)
        approval = {
            'schema_version': 1, 'approved': True, 'decision': 'APPROVE',
            'decision_maker': decision_maker,
            'decision_timestamp': datetime.now(UTC).isoformat(),
            'artifact_sha256': artifacts,
            'confirmation': expected,
        }
        write_json(root / 'audit' / 'final_release_approval.json', approval)
        result = run_final_consistency_check(root, final_approval=approval)
        report = read_json(root / 'audit' / 'final_release_report.json')
        if not report.get('release_permitted'):
            raise ValueError('final release gate refused the current artifacts')
        package = build_submission_package(root, release_name)
        states.record_event(
            event_type='FINAL_APPROVAL_RECORDED', action='final_release', actor=actor,
            details={'decision_maker': decision_maker,
                     'release_name': release_name,
                     'artifact_count': len(package.manifest.artifacts)},
        )
        self._sync(states.transition(
            ProjectState.RELEASED, action='build_release_package', actor=actor,
            details={'release_name': release_name},
        ))
        return package

    def dashboard(self, project_root: str | Path) -> dict[str, Any]:
        root, states = self._services(project_root)
        state = states.load()
        comments_raw = read_json(root / 'working' / 'reviewer_comments.json')
        comments = [ReviewerComment.model_validate(item) for item in comments_raw]
        source_counts = Counter(
            f'Reviewer {item.reviewer_number}' if item.reviewer_number else item.reviewer_source.value
            for item in comments
        )
        plan_path = root / 'working' / 'revision_plan.json'
        plan = read_json(plan_path) if plan_path.is_file() else {'actions': []}
        actions = [RevisionAction.model_validate(item) for item in plan.get('actions', [])]
        draft_path = root / 'working' / 'revision_drafts.json'
        drafts_payload = read_json(draft_path) if draft_path.is_file() else {'drafts': []}
        drafts = [RevisionDraft.model_validate(item['draft']) for item in drafts_payload.get('drafts', [])]
        qa_path = root / 'audit' / 'scientific_qa_report.json'
        qa = read_json(qa_path) if qa_path.is_file() else {}
        response_path = root / 'working' / 'response_package.json'
        response = read_json(response_path) if response_path.is_file() else {}
        response_entries = [
            item for section in response.get('sections', [])
            for item in section.get('entries', [])
        ]
        release_path = root / 'audit' / 'final_release_report.json'
        release = read_json(release_path) if release_path.is_file() else {}
        return {
            'project_status': state.state.value,
            'total_comments': len(comments),
            'comments_by_reviewer': dict(sorted(source_counts.items())),
            'manual_review_count': sum(item.manual_review_required for item in comments),
            'revision_actions': len(actions),
            'approved_actions': sum(item.approval_state.value == 'APPROVED' for item in actions),
            'draft_texts_awaiting_approval': sum(
                item.approval_state.value == 'PENDING' for item in drafts
            ),
            'qa_blockers': int(qa.get('blocker_count', 0)),
            'verified_responses': sum(
                item.get('response_status') == 'VERIFIED' for item in response_entries
            ),
            'release_readiness': release.get('readiness', 'NOT_EVALUATED'),
            'next_recommended_action': state.next_required_action,
            'blockers': state.blockers,
        }

    def file_inventory(self, project_root: str | Path) -> list[dict[str, Any]]:
        root = Path(project_root).expanduser().resolve()
        rows: list[dict[str, Any]] = []
        for folder in ('input', 'outputs'):
            for path in sorted((root / folder).rglob('*')):
                if path.is_file():
                    rows.append({
                        'role': folder,
                        'file_name': path.relative_to(root / folder).as_posix(),
                        'size_bytes': path.stat().st_size,
                        'sha256': sha256_file(path),
                    })
        versions = root / 'audit' / 'document_version_manifest.json'
        version_map = {}
        if versions.is_file():
            version_payload = read_json(versions)
            for item in version_payload.get('versions', []):
                version_map[item.get('file_name')] = item.get('version')
            latest = version_payload.get('latest_output_version')
            version_map['Revised_Manuscript_Highlighted.docx'] = latest
            version_map['Revised_Manuscript_Clean.docx'] = latest
        for row in rows:
            row['version'] = version_map.get(Path(row['file_name']).name)
        return rows

    def audit_timeline(self, project_root: str | Path) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode='json')
            for item in ProjectStateService(project_root).timeline()
        ]
