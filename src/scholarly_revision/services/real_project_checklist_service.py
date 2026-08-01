'''Read-only, artifact-backed readiness checklist for a real revision project.'''

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.agent_task import AgentTaskStatus, AgentTaskType
from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.agent_run_registry import AgentRunRegistry
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.services.project_workspace import sha256_file


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    stage: str
    check_id: str
    label: str
    complete: bool
    detail: str


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return default


def _items(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get(key, [])
        return value if isinstance(value, list) else []
    return []


class RealProjectChecklistService:
    '''Derive workflow readiness without changing scientific state.'''

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()

    def _source_hashes_ok(self) -> tuple[bool, str]:
        report = _json(self.root / 'audit' / 'intake_report.json', {})
        recorded = report.get('hash_values', {}) if isinstance(report, dict) else {}
        if not recorded:
            return False, 'No intake hash inventory is available.'
        mismatches = []
        for relative, digest in recorded.items():
            path = self.root / str(relative)
            if not path.is_file() or sha256_file(path) != digest:
                mismatches.append(str(relative))
        return not mismatches, (
            'All copied inputs match intake hashes.'
            if not mismatches else 'Missing or changed inputs: ' + ', '.join(mismatches)
        )

    def _agent_gate(self, task_type: AgentTaskType) -> tuple[bool, str]:
        tasks = [
            task for task in AgentRunRegistry(self.root).tasks()
            if task.task_type is task_type
        ]
        if not tasks:
            return True, 'Optional semantic lane was not used.'
        bad = [
            task.task_id for task in tasks
            if task.status not in {AgentTaskStatus.APPROVED, AgentTaskStatus.IMPORTED}
        ]
        return not bad, (
            'Every semantic output passed validation and explicit author review.'
            if not bad else 'Unreviewed semantic tasks: ' + ', '.join(bad)
        )

    def evaluate(self) -> dict[str, Any]:
        root = self.root
        state = ProjectStateService(root).load()
        comments = _json(root / 'working' / 'reviewer_comments.json', [])
        comments = comments if isinstance(comments, list) else []
        comment_ids = {str(item.get('comment_id')) for item in comments}
        intake = _json(root / 'audit' / 'intake_report.json', {})
        hashes_ok, hashes_detail = self._source_hashes_ok()

        gap = _json(root / 'working' / 'gap_analysis_imported.json', {})
        assessments = _items(gap, 'assessments')
        gap_ids = {str(item.get('comment_id')) for item in assessments}
        gap_agent_ok, gap_agent_detail = self._agent_gate(AgentTaskType.GAP_ANALYSIS)

        plan = _json(root / 'working' / 'revision_plan.json', {})
        actions = _items(plan, 'actions')
        action_by_id = {str(item.get('action_id')): item for item in actions}
        plan_explicit = bool(actions) and all(
            item.get('approval_state') not in {None, 'PENDING'}
            for item in actions
        )

        drafts_payload = _json(root / 'working' / 'revision_drafts.json', {})
        drafts = [
            item.get('draft', item) for item in _items(drafts_payload, 'drafts')
            if isinstance(item, dict)
        ]
        approved_sources_only = bool(drafts) and all(
            action_by_id.get(str(item.get('action_id')), {}).get('approval_state')
            == 'APPROVED' for item in drafts
        )
        text_explicit = bool(drafts) and all(
            item.get('approval_state') != 'PENDING' for item in drafts
        )

        application_report = _json(root / 'audit' / 'revision_application_report.json', {})
        output_report = _json(
            root / 'audit' / 'revision_output_verification_report.json', {}
        )
        application_ok = bool(application_report) and all((
            (root / 'outputs' / 'Revised_Manuscript_Highlighted.docx').is_file(),
            (root / 'outputs' / 'Revised_Manuscript_Clean.docx').is_file(),
            bool(output_report),
            hashes_ok,
        ))

        qa = _json(root / 'audit' / 'scientific_qa_report.json', {})
        qa_ok = bool(qa) and int(qa.get('blocker_count', 1)) == 0
        response = _json(root / 'working' / 'response_package.json', {})
        entries = [
            item for section in response.get('sections', [])
            for item in section.get('entries', [])
        ] if isinstance(response, dict) else []
        response_ids = {str(item.get('comment_id')) for item in entries}
        response_ok = bool(entries) and response_ids == comment_ids and all(
            item.get('response_status') == 'VERIFIED' for item in entries
        )
        visual = _json(root / 'audit' / 'manual_visual_qa_decisions.json', {})
        visual_ok = bool(visual) and not visual.get('blocking_item_ids', [])
        release = _json(root / 'audit' / 'final_release_report.json', {})

        items = [
            ChecklistItem('INTAKE', 'source_files_copied_and_hashed',
                          'Source files copied and hashed', hashes_ok, hashes_detail),
            ChecklistItem('INTAKE', 'comments_extracted',
                          'Reviewer comments extracted', bool(comments),
                          f'{len(comments)} stable comment records found.'),
            ChecklistItem('INTAKE', 'manual_boundaries_reviewed',
                          'Manual extraction boundaries reviewed',
                          int(intake.get('manual_review_required_count', 0)) == 0
                          or state.state not in {
                              ProjectState.NEW, ProjectState.INTAKE_PENDING,
                              ProjectState.INTAKE_REVIEW,
                          },
                          'Intake review must be explicitly completed when boundaries are flagged.'),
            ChecklistItem('GAP ANALYSIS', 'complete_comment_coverage',
                          'Every comment covered by validated gap analysis',
                          bool(comment_ids) and gap_ids == comment_ids,
                          f'{len(gap_ids)} of {len(comment_ids)} comments covered.'),
            ChecklistItem('GAP ANALYSIS', 'semantic_author_review',
                          'Semantic output explicitly reviewed', gap_agent_ok,
                          gap_agent_detail),
            ChecklistItem('REVISION PLAN', 'actions_generated',
                          'Revision actions generated', bool(actions),
                          f'{len(actions)} action records found.'),
            ChecklistItem('REVISION PLAN', 'all_decisions_explicit',
                          'Every Gate 1 decision is explicit', plan_explicit,
                          'No pending or absent action approval states are permitted.'),
            ChecklistItem('DRAFTING', 'approved_actions_only',
                          'Drafts originate only from approved actions',
                          approved_sources_only,
                          'Every draft action must have explicit Gate 1 approval.'),
            ChecklistItem('DRAFTING', 'evidence_requirements_visible',
                          'Evidence requirements remain visible', bool(actions) and all(
                              'evidence_requirements' in item for item in actions
                          ), 'Plan actions retain explicit evidence requirement lists.'),
            ChecklistItem('TEXT APPROVAL', 'all_text_decisions_explicit',
                          'Every Gate 2 text decision is explicit', text_explicit,
                          'No draft may remain in PENDING approval state.'),
            ChecklistItem('APPLICATION', 'immutable_source_and_outputs',
                          'Source immutable; highlighted and clean outputs verified',
                          application_ok,
                          'Input hashes, both derived manuscripts, and verification report are required.'),
            ChecklistItem('SCIENTIFIC QA', 'deterministic_auditors_clear',
                          'Deterministic QA executed with explicit blockers', qa_ok,
                          f'QA blocker count: {qa.get('blocker_count', 'not run')}.'),
            ChecklistItem('RESPONSE', 'verified_complete_response',
                          'Every comment represented and every claimed change verified',
                          response_ok,
                          f'{len(response_ids)} of {len(comment_ids)} comments represented.'),
            ChecklistItem('VISUAL QA', 'manual_artifact_decisions',
                          'Manual visual artifact decisions recorded', visual_ok,
                          'All pages and complex Word objects require recorded decisions.'),
            ChecklistItem('RELEASE', 'release_permitted',
                          'Release package permitted by deterministic gate',
                          bool(release.get('release_permitted')),
                          'Final release report must explicitly permit release.'),
        ]
        return {
            'project_state': state.state.value,
            'generated_at': datetime.now(UTC).isoformat(),
            'complete': all(item.complete for item in items),
            'items': [asdict(item) for item in items],
        }

    def record_pilot_approval(
        self, *, actor: str, checks: dict[str, bool], note: str = '',
    ) -> Path:
        if not actor.strip():
            raise ValueError('pilot approval requires a named decision maker')
        required = {
            'context_minimization_reviewed', 'transmission_gate_verified',
            'import_gate_verified', 'additional_backups_verified',
            'complex_word_objects_reviewed', 'cross_document_consistency_verified',
        }
        if set(checks) != required or not all(checks.values()):
            raise ValueError('every pilot check requires an explicit positive decision')
        payload = {
            'approved': True, 'decision_maker': actor.strip(),
            'decision_timestamp': datetime.now(UTC).isoformat(),
            'checks': checks, 'note': note, 'approval_inferred': False,
        }
        path = self.root / 'audit' / 'pilot_checks.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        temporary.replace(path)
        ProjectStateService(self.root).record_event(
            event_type='PILOT_CHECKS_APPROVED',
            action='record_pilot_checks', actor=actor.strip(),
            details={'checks': sorted(required)},
        )
        return path
