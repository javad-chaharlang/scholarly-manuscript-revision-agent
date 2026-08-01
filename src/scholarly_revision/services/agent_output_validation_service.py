'''Strict semantic-output validation against governed project records.'''
from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from pydantic import ValidationError
from scholarly_revision.models.agent_context import AgentContextManifest
from scholarly_revision.models.agent_task import AgentTask, AgentTaskType
from scholarly_revision.models.enums import ApprovalState, RevisionDraftStatus, RevisionStatus
from scholarly_revision.models.gap_analysis import GapAnalysisAssessment
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.revision_draft import RevisionDraft
from scholarly_revision.models.response_package import ResponseEntry, ResponseStatus
from scholarly_revision.models.scientific_audit import AuditIssue, AuditIssueStatus
from scholarly_revision.services.gap_analysis_service import read_json

_LOCATION = re.compile(r'\b(?:page|pages|p\.|line|lines)\s*#?\s*\d+\b', re.I)
_NUMBER = re.compile(r'(?<![A-Za-z0-9-])[-+]?\d+(?:\.\d+)?%?(?![A-Za-z0-9-])')
_EXPERIMENT = re.compile(
    r'\b(?:we|the authors?)\s+(?:conducted|performed|ran|measured|tested|evaluated)\b',
    re.I,
)
_AUTO_STATES = {'APPROVED', 'APPLIED', 'VERIFIED', 'IMPORTED', 'RELEASED'}
_NARRATIVE_FIELDS = {
    'interpretation', 'rationale', 'proposed_text', 'analysis',
    'author_response', 'changes_made', 'description',
    'proposed_revision_summary', 'drafting_rationale', 'uncertainties',
    'risks', 'missing_elements', 'unresolved_questions',
    'verified_locations', 'applied_location', 'location',
}

@dataclass(frozen=True, slots=True)
class AgentValidationResult:
    valid: bool
    normalized_output: dict[str, Any] | None
    errors: tuple[dict[str, str], ...]
    warnings: tuple[str, ...] = ()
    def report(self) -> dict[str, Any]:
        return asdict(self)

def _records(path: Path, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []

def _identifiers(records: list[dict[str, Any]], names: tuple[str, ...]) -> set[str]:
    result = set()
    for item in records:
        for name in names:
            if item.get(name):
                result.add(str(item[name]))
    return result

def _walk(value: Any, path: str = '$'):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from _walk(nested, f'{path}.{key}')
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk(nested, f'{path}[{index}]')
    else:
        yield path, value

class AgentOutputValidationService:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()

    def validate(
        self, task: AgentTask, context: AgentContextManifest, raw: dict[str, Any],
    ) -> AgentValidationResult:
        errors: list[dict[str, str]] = []
        def reject(code: str, message: str) -> None:
            errors.append({'code': code, 'message': message})
        for path, value in _walk(raw):
            if path.rsplit('.', 1)[-1] in {
                'status', 'approval_state', 'draft_status', 'response_status',
            } and str(value) in _AUTO_STATES:
                reject('AUTOMATIC_APPROVAL_STATE', f'{path} cannot be {value}')
        try:
            normalized = self._validate_type(task, context, raw, reject)
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            reject('PYDANTIC_OR_SEMANTIC_VALIDATION', str(exc))
            normalized = None
        if normalized is not None:
            self._integrity_checks(context, normalized, reject)
        return AgentValidationResult(
            valid=not errors, normalized_output=normalized if not errors else None,
            errors=tuple(errors),
        )

    def _source_data(self) -> tuple[dict[str, ReviewerComment], dict[str, RevisionAction], dict[str, Any]]:
        comments = {
            item.comment_id: item for item in (
                ReviewerComment.model_validate(raw) for raw in read_json(
                    self.root / 'working' / 'reviewer_comments.json'
                )
            )
        }
        plan_path = self.root / 'working' / 'revision_plan.json'
        plan = read_json(plan_path) if plan_path.is_file() else {'actions': []}
        actions = {
            item.action_id: item for item in (
                RevisionAction.model_validate(raw) for raw in plan.get('actions', [])
            )
        }
        structure_path = self.root / 'working' / 'manuscript_structure.json'
        structure = read_json(structure_path) if structure_path.is_file() else {'elements': []}
        return comments, actions, structure

    def _validate_type(self, task, context, raw, reject):
        comments, actions, structure = self._source_data()
        expected = set(task.related_comment_ids)
        if task.task_type is AgentTaskType.COMMENT_INTERPRETATION:
            records = [ReviewerComment.model_validate(item) for item in raw['interpretations']]
            self._exact_comment_scope(records, expected, comments)
            return {'interpretations': [item.model_dump(mode='json') for item in records]}
        if task.task_type is AgentTaskType.GAP_ANALYSIS:
            records = [GapAnalysisAssessment.model_validate(item) for item in raw['assessments']]
            ids = [item.comment_id for item in records]
            if len(ids) != len(set(ids)) or set(ids) != expected:
                raise ValueError('gap analysis requires exactly one record for every requested comment')
            for item in records:
                if item.original_comment != comments[item.comment_id].original_comment:
                    raise ValueError(f'exact reviewer comment changed: {item.comment_id}')
                if item.coverage_status is None:
                    raise ValueError(f'missing coverage status: {item.comment_id}')
            return {'assessments': [item.model_dump(mode='json') for item in records]}
        if task.task_type is AgentTaskType.REVISION_PLAN_DRAFT:
            raw_actions = raw['actions']
            records = [RevisionAction.model_validate(item) for item in raw_actions]
            covered = {comment_id for item in records for comment_id in item.comment_ids}
            if expected and not expected.issubset(covered):
                raise ValueError('revision plan draft does not cover every requested comment')
            known_sections = {
                str(value)
                for item in structure.get('elements', []) if isinstance(item, dict)
                for value in (
                    item.get('section'), item.get('section_path'),
                    item.get('section_id'),
                )
                if value
            }
            known_sections.update(
                str(value) for value in structure.get('section_order', []) if value
            )
            known_sections.update(
                str(value)
                for item in structure.get('outline', []) if isinstance(item, dict)
                for value in (item.get('title'), item.get('section_id'))
                if value
            )
            for source, item in zip(raw_actions, records):
                if set(item.comment_ids) - set(comments):
                    raise ValueError(f'unknown comment ID in {item.action_id}')
                if known_sections and item.target_section not in known_sections:
                    raise ValueError(f'unknown target section in {item.action_id}')
                if item.status is not RevisionStatus.PLANNED:
                    raise ValueError('revision plan drafts must remain PLANNED')
                if item.approval_state is not ApprovalState.PENDING:
                    raise ValueError('revision plan drafts cannot be approved')
                for key in ('evidence_requirements', 'unresolved_questions'):
                    if key not in source:
                        raise ValueError(f'{item.action_id} must explicitly include {key}')
            return {'actions': [item.model_dump(mode='json') for item in records]}
        if task.task_type is AgentTaskType.REVISION_TEXT_DRAFT:
            records = [RevisionDraft.model_validate(item) for item in raw['drafts']]
            if task.related_action_ids and {
                item.action_id for item in records
            } != set(task.related_action_ids):
                raise ValueError('revision text draft must exactly cover requested actions')
            aliases = {
                str(item.get(key)): item
                for item in structure.get('elements', []) if isinstance(item, dict)
                for key in ('element_id', 'paragraph_id') if item.get(key)
            }
            for item in records:
                action = actions.get(item.action_id)
                if action is None or action.approval_state is not ApprovalState.APPROVED:
                    raise ValueError(f'draft requires approved RevisionAction: {item.action_id}')
                if item.comment_ids != action.comment_ids:
                    raise ValueError(f'draft comment IDs differ from action: {item.draft_id}')
                if not item.target_element_ids or any(
                    identifier not in aliases for identifier in item.target_element_ids
                ):
                    raise ValueError(f'draft target is not exact: {item.draft_id}')
                if item.draft_status is RevisionDraftStatus.APPLIED:
                    raise ValueError('agent revision text cannot be APPLIED')
                if item.draft_status not in {
                    RevisionDraftStatus.DRAFTED,
                    RevisionDraftStatus.AWAITING_TEXT_APPROVAL,
                }:
                    raise ValueError('agent revision text must remain an unapproved draft')
            return {'drafts': [item.model_dump(mode='json') for item in records]}
        if task.task_type is AgentTaskType.SEMANTIC_QA_REVIEW:
            records = [AuditIssue.model_validate(item) for item in raw['findings']]
            if any(item.status is not AuditIssueStatus.OPEN for item in records):
                raise ValueError('semantic QA findings must remain OPEN')
            return {'findings': [item.model_dump(mode='json') for item in records]}
        if task.task_type is AgentTaskType.RESPONSE_LETTER_DRAFT:
            records = [ResponseEntry.model_validate(item) for item in raw['entries']]
            ids = [item.comment_id for item in records]
            if len(ids) != len(set(ids)) or set(ids) != expected:
                raise ValueError('response draft requires one record for every requested comment')
            changes = _records(self.root / 'audit' / 'change_log.json', ('changes',))
            verified_changes = {
                str(item.get('change_id')) for item in changes
                if item.get('verification_status') == 'VERIFIED'
            }
            for item in records:
                if item.exact_comment != comments[item.comment_id].original_comment:
                    raise ValueError(f'exact reviewer comment changed: {item.comment_id}')
                if set(item.related_change_ids) - verified_changes:
                    raise ValueError(f'response claims an unverified change: {item.comment_id}')
                if item.changes_made and not item.related_change_ids:
                    raise ValueError(f'response claims changes without Change Log IDs: {item.comment_id}')
                if item.response_status not in {
                    ResponseStatus.DRAFTED, ResponseStatus.AUTHOR_REVIEW,
                } or item.author_approved:
                    raise ValueError('agent response output cannot claim author approval')
                context_text = json.dumps(context.transmitted_payload, ensure_ascii=False)
                if any(location not in context_text for location in item.verified_locations):
                    raise ValueError(f'response contains an unverified location: {item.comment_id}')
            return {'entries': [item.model_dump(mode='json') for item in records]}
        key = (
            'reference_needs'
            if task.task_type is AgentTaskType.REFERENCE_NEED_ANALYSIS else 'notes'
        )
        allowed = {
            'record_id', 'related_comment_ids', 'analysis', 'evidence_ids', 'uncertainties',
        }
        records = raw[key]
        if not isinstance(records, list):
            raise ValueError(f'{key} must be a list')
        normalized = []
        for item in records:
            if not isinstance(item, dict) or set(item) != allowed:
                raise ValueError(f'{key} contains unsupported or missing fields')
            if set(item['related_comment_ids']) - set(comments):
                raise ValueError(f'{key} references an unknown comment')
            if not str(item['record_id']).strip() or not str(item['analysis']).strip():
                raise ValueError(f'{key} requires record_id and analysis')
            normalized.append(item)
        return {key: normalized}

    @staticmethod
    def _exact_comment_scope(records, expected, comments) -> None:
        ids = [item.comment_id for item in records]
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError('interpretation output must exactly cover requested comments')
        for item in records:
            if item.original_comment != comments[item.comment_id].original_comment:
                raise ValueError(f'exact reviewer comment changed: {item.comment_id}')

    def _integrity_checks(self, context, normalized, reject) -> None:
        context_text = json.dumps(context.transmitted_payload, ensure_ascii=False)
        allowed_evidence = {
            str(item.get('evidence_id'))
            for item in context.transmitted_payload.get('evidence_records', [])
            if isinstance(item, dict) and item.get('evidence_id')
        }
        allowed_references = {
            str(item.get(key))
            for item in context.transmitted_payload.get('references', [])
            if isinstance(item, dict)
            for key in ('reference_id', 'doi')
            if item.get(key)
        }
        for path, value in _walk(normalized):
            key = path.rsplit('.', 1)[-1].split('[', 1)[0]
            segments = {
                part.split('[', 1)[0] for part in path.split('.')[1:]
            }
            narrative = bool(segments & _NARRATIVE_FIELDS)
            if narrative and isinstance(value, str) and _LOCATION.search(value):
                for token in _LOCATION.findall(value):
                    if token not in context_text:
                        reject('UNVERIFIED_LOCATION', f'{path} contains {token!r}')
            if key in {'evidence_id', 'related_evidence_ids', 'evidence_ids'}:
                values = value if isinstance(value, list) else [value]
                for identifier in values:
                    if identifier and str(identifier) not in allowed_evidence:
                        reject('INVENTED_EVIDENCE', f'{path} references {identifier}')
            if key in {'reference_id', 'related_reference_ids', 'reference_ids', 'doi'}:
                values = value if isinstance(value, list) else [value]
                for identifier in values:
                    if identifier and str(identifier) not in allowed_references:
                        reject('INVENTED_REFERENCE', f'{path} references {identifier}')
            if narrative and isinstance(value, str) and _EXPERIMENT.search(value):
                if value not in context_text:
                    reject('UNSUPPORTED_EXPERIMENT_CLAIM', f'{path} claims performed work')
            if narrative and isinstance(value, str) and _NUMBER.search(value):
                for token in _NUMBER.findall(value):
                    if token not in context_text:
                        reject('UNSUPPORTED_NUMERIC_CLAIM', f'{path} contains {token}')
