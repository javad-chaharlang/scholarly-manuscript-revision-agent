'''Deterministic preparation and strict import of Phase 5 drafting packages.'''

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.enums import (
    ApprovalState,
    ChangeType,
    RevisionDraftStatus,
    RevisionOperation,
)
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.revision_draft import RevisionDraft
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.project_workspace import sha256_file


_ABSOLUTE_LOCATION = re.compile(
    r'\b(?:page|pages|p\.|line|lines)\s*#?\s*\d+\b', re.IGNORECASE
)
_COMPLEX_ELEMENT_TYPES = {'equation', 'reference_entry', 'reference_section_heading'}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _load_list(path: Path, label: str) -> list[Any]:
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f'{label} must contain a list')
    return payload


def load_project_revision_sources(
    project_root: str | Path,
) -> tuple[list[ReviewerComment], list[RevisionAction], dict[str, Any], str]:
    root = Path(project_root).expanduser().resolve()
    comments = [
        ReviewerComment.model_validate(item)
        for item in _load_list(root / 'working' / 'reviewer_comments.json', 'reviewer_comments.json')
    ]
    plan = read_json(root / 'working' / 'revision_plan.json')
    if not isinstance(plan, dict) or not isinstance(plan.get('actions'), list):
        raise ValueError('revision_plan.json must contain an actions list')
    actions = [RevisionAction.model_validate(item) for item in plan['actions']]
    structure = read_json(root / 'working' / 'manuscript_structure.json')
    if not isinstance(structure, dict) or not isinstance(structure.get('elements'), list):
        raise ValueError('manuscript_structure.json must contain structural elements')
    gap_input = read_json(root / 'working' / 'gap_analysis_input.json')
    try:
        source_hash = str(gap_input['manuscript_source']['sha256'])
    except (KeyError, TypeError) as exc:
        raise ValueError('gap_analysis_input.json lacks manuscript source SHA-256') from exc
    return comments, actions, structure, source_hash


def _approved_action(action: RevisionAction) -> bool:
    return (
        action.approval_state is ApprovalState.APPROVED
        and action.approval_decision in {'APPROVE', 'APPROVE_WITH_MODIFICATION'}
    )


def _element_index(structure: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    elements = structure['elements']
    aliases: dict[str, dict[str, Any]] = {}
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError('manuscript structural elements must be objects')
        for key in ('element_id', 'paragraph_id'):
            identifier = element.get(key)
            if identifier:
                existing = aliases.get(str(identifier))
                if existing is not None and existing is not element:
                    raise ValueError(f'ambiguous structural identifier: {identifier}')
                aliases[str(identifier)] = element
    return aliases, elements


def _table_id(elements: list[dict[str, Any]], table_index: int) -> str | None:
    for element in elements:
        if element.get('element_type') == 'table' and element.get('table_index') == table_index:
            return str(element['element_id'])
    return None


def operation_for_action(action: RevisionAction, element: dict[str, Any]) -> RevisionOperation:
    element_type = element.get('element_type')
    if action.change_type is ChangeType.DELETION:
        return RevisionOperation.DELETE_PARAGRAPH
    if action.change_type is ChangeType.ADDITION:
        return RevisionOperation.INSERT_AFTER
    if element_type == 'heading':
        return RevisionOperation.REPLACE_HEADING
    if element_type == 'figure_caption':
        return RevisionOperation.REPLACE_FIGURE_CAPTION
    if element_type == 'table_caption':
        return RevisionOperation.REPLACE_TABLE_CAPTION
    if element_type == 'table_cell_paragraph':
        return RevisionOperation.REPLACE_TABLE_CELL
    return RevisionOperation.REPLACE_PARAGRAPH


def _neighbor_context(
    elements: list[dict[str, Any]], target: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    position = elements.index(target)
    preceding = next(
        (item for item in reversed(elements[:position]) if str(item.get('text') or '').strip()),
        None,
    )
    following = next(
        (item for item in elements[position + 1:] if str(item.get('text') or '').strip()),
        None,
    )
    return preceding, following


def _approved_action_text(action: RevisionAction) -> str:
    if action.approval_decision == 'APPROVE_WITH_MODIFICATION':
        return action.modified_action_text or ''
    return action.proposed_revision_summary or action.proposed_text or ''


def build_revision_drafting_package(project_root: str | Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    '''Build context and a blank template without generating revision prose.'''

    root = Path(project_root).expanduser().resolve()
    comments, actions, structure, source_hash = load_project_revision_sources(root)
    comment_map = {item.comment_id: item for item in comments}
    aliases, elements = _element_index(structure)
    now = datetime.now(UTC)
    input_actions: list[dict[str, Any]] = []
    template_entries: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    approved = [action for action in actions if _approved_action(action)]

    for number, action in enumerate(approved, start=1):
        unknown_comments = sorted(set(action.comment_ids) - set(comment_map))
        if unknown_comments:
            raise ValueError(
                f'{action.action_id} references unknown comment IDs: '
                + ', '.join(unknown_comments)
            )
        target_id = (action.target_object or '').strip()
        target = aliases.get(target_id)
        exact_comments = [
            {
                'comment_id': comment_id,
                'exact_comment': comment_map[comment_id].original_comment,
            }
            for comment_id in action.comment_ids
        ]
        base_context = {
            'action_id': action.action_id,
            'comment_ids': action.comment_ids,
            'exact_reviewer_comments': exact_comments,
            'approved_action_text': _approved_action_text(action),
            'manuscript_section_context': action.target_section,
            'target_structural_element': target,
            'preceding_paragraph_context': None,
            'following_paragraph_context': None,
            'evidence_requirements': action.evidence_requirements,
            'reference_requirements': action.reference_requirements,
            'highlight': action.highlight.value,
            'unresolved_questions': action.unresolved_questions,
        }
        if not target_id:
            base_context['blocking_reason'] = 'Approved action has no exact target structural element ID.'
            input_actions.append(base_context)
            blocked.append({'action_id': action.action_id, 'reason': base_context['blocking_reason']})
            continue
        if target is None:
            base_context['blocking_reason'] = f'Unknown target structural element ID: {target_id}'
            input_actions.append(base_context)
            blocked.append({'action_id': action.action_id, 'reason': base_context['blocking_reason']})
            continue
        if target.get('uncertain'):
            base_context['blocking_reason'] = 'Target structural element is marked uncertain and needs manual confirmation.'
            input_actions.append(base_context)
            blocked.append({'action_id': action.action_id, 'reason': base_context['blocking_reason']})
            continue
        if target.get('element_type') in _COMPLEX_ELEMENT_TYPES:
            base_context['blocking_reason'] = (
                f"Target type {target.get('element_type')} is manual-only in Phase 5."
            )
            input_actions.append(base_context)
            blocked.append({'action_id': action.action_id, 'reason': base_context['blocking_reason']})
            continue

        preceding, following = _neighbor_context(elements, target)
        base_context['preceding_paragraph_context'] = preceding
        base_context['following_paragraph_context'] = following
        input_actions.append(base_context)
        operation = operation_for_action(action, target)
        original_text = str(target.get('text') or '')
        table_index = target.get('table_index')
        draft = RevisionDraft(
            draft_id=f'DRAFT-{number:04d}',
            action_id=action.action_id,
            comment_ids=action.comment_ids,
            source_document_hash=source_hash,
            target_element_ids=[target_id],
            target_section=action.target_section,
            operation=operation,
            original_text_snapshot=original_text,
            original_text_hash=sha256_text(original_text),
            proposed_text='',
            drafting_rationale=action.rationale,
            evidence_ids=[],
            reference_ids=[],
            scientific_claim_ids=[],
            highlight=action.highlight,
            draft_status=RevisionDraftStatus.PREPARED,
            deletion_justification=(
                action.author_note or action.rationale
                if operation is RevisionOperation.DELETE_PARAGRAPH
                else None
            ),
            table_id=(
                _table_id(elements, int(table_index))
                if operation is RevisionOperation.REPLACE_TABLE_CELL
                and table_index is not None else None
            ),
            table_row=(
                int(target['row_index'])
                if operation is RevisionOperation.REPLACE_TABLE_CELL else None
            ),
            table_column=(
                int(target['cell_index'])
                if operation is RevisionOperation.REPLACE_TABLE_CELL else None
            ),
            unresolved_questions=action.unresolved_questions,
            created_at=now,
            updated_at=now,
        )
        template_entries.append({
            'action_id': action.action_id,
            'exact_reviewer_comments': exact_comments,
            'approved_action_text': _approved_action_text(action),
            'draft': draft.model_dump(mode='json'),
        })

    common = {
        'schema_version': 1,
        'prepared_at': now.isoformat(),
        'source_document_hash': source_hash,
        'approved_action_count': len(approved),
        'manuscript_modified': False,
        'scientific_revision_text_generated_by_deterministic_code': False,
    }
    drafting_input = {**common, 'actions': input_actions}
    template = {
        **common,
        'instructions': (
            'Complete only proposed_text and evidence/reference/claim links. '
            'Do not alter action, comment, target, snapshot, hash, or context fields.'
        ),
        'drafts': template_entries,
    }
    report = {
        **common,
        'drafts_prepared': len(template_entries),
        'actions_blocked': len(blocked),
        'blocked_actions': blocked,
        'blank_proposed_text_count': len(template_entries),
    }
    return drafting_input, template, report


def _exact_comment_map(entry: dict[str, Any]) -> dict[str, str]:
    raw = entry.get('exact_reviewer_comments')
    if not isinstance(raw, list):
        raise ValueError('each draft entry requires exact_reviewer_comments')
    result: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict) or set(item) != {'comment_id', 'exact_comment'}:
            raise ValueError('exact_reviewer_comments entries are malformed')
        comment_id = str(item['comment_id'])
        if comment_id in result:
            raise ValueError(f'duplicate exact reviewer comment: {comment_id}')
        result[comment_id] = str(item['exact_comment'])
    return result


def import_revision_drafts(
    project_root: str | Path,
    draft_file: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    '''Strictly validate completed drafts; never repair malformed content.'''

    root = Path(project_root).expanduser().resolve()
    source = Path(draft_file).expanduser().resolve()
    payload = read_json(source)
    if not isinstance(payload, dict) or not isinstance(payload.get('drafts'), list):
        raise ValueError('completed revision draft file must contain a drafts list')
    comments, actions, structure, source_hash = load_project_revision_sources(root)
    comment_map = {item.comment_id: item for item in comments}
    action_map = {item.action_id: item for item in actions}
    aliases, _ = _element_index(structure)
    prepared = read_json(root / 'working' / 'revision_draft_template.json')
    prepared_ids = {
        item['draft']['draft_id']
        for item in prepared.get('drafts', [])
        if isinstance(item, dict) and isinstance(item.get('draft'), dict)
    }

    imported_entries: list[dict[str, Any]] = []
    seen_drafts: set[str] = set()
    for entry in payload['drafts']:
        if not isinstance(entry, dict) or not isinstance(entry.get('draft'), dict):
            raise ValueError('each completed draft entry must contain a draft object')
        draft = RevisionDraft.model_validate(entry['draft'])
        if draft.draft_id in seen_drafts:
            raise ValueError(f'duplicate draft ID: {draft.draft_id}')
        seen_drafts.add(draft.draft_id)
        if draft.draft_id not in prepared_ids:
            raise ValueError(f'unknown draft ID: {draft.draft_id}')
        action = action_map.get(draft.action_id)
        if action is None:
            raise ValueError(f'unknown action ID: {draft.action_id}')
        if not _approved_action(action):
            raise ValueError(f'unapproved action ID: {draft.action_id}')
        if draft.comment_ids != action.comment_ids:
            raise ValueError(f'{draft.draft_id} comment IDs do not match its action')
        exact = _exact_comment_map(entry)
        if set(exact) != set(draft.comment_ids):
            raise ValueError(f'{draft.draft_id} exact comment IDs do not match its action')
        for comment_id, exact_text in exact.items():
            if comment_id not in comment_map:
                raise ValueError(f'unknown comment ID: {comment_id}')
            if exact_text != comment_map[comment_id].original_comment:
                raise ValueError(f'{comment_id} exact reviewer comment was altered')
        if draft.source_document_hash != source_hash:
            raise ValueError(f'{draft.draft_id} source document hash mismatch')
        if not draft.target_element_ids:
            raise ValueError(f'{draft.draft_id} has no target element ID')
        targets: list[dict[str, Any]] = []
        for target_id in draft.target_element_ids:
            target = aliases.get(target_id)
            if target is None:
                raise ValueError(f'{draft.draft_id} targets unknown structural element {target_id}')
            targets.append(target)
        snapshot = '\n'.join(str(item.get('text') or '') for item in targets)
        if draft.original_text_snapshot != snapshot:
            raise ValueError(f'{draft.draft_id} original text snapshot mismatch')
        if draft.original_text_hash != sha256_text(snapshot):
            raise ValueError(f'{draft.draft_id} original-text hash mismatch')
        if draft.operation is not RevisionOperation.DELETE_PARAGRAPH and not draft.proposed_text.strip():
            raise ValueError(f'{draft.draft_id} has empty replacement text')
        if draft.scientific_claim_ids and not draft.evidence_ids:
            raise ValueError(f'{draft.draft_id} proposes claims without evidence links')
        if action.evidence_requirements and draft.scientific_claim_ids and not draft.evidence_ids:
            raise ValueError(f'{draft.draft_id} lacks required evidence links')
        location_text = ' '.join([
            draft.target_section,
            draft.drafting_rationale,
            draft.author_note or '',
            *draft.unresolved_questions,
        ])
        if _ABSOLUTE_LOCATION.search(location_text):
            verified = set(draft.verified_locations)
            matches = {match.group(0) for match in _ABSOLUTE_LOCATION.finditer(location_text)}
            if not matches.issubset(verified):
                raise ValueError(f'{draft.draft_id} contains an unverified page/line reference')
        if entry.get('approved_action_text') != _approved_action_text(action):
            raise ValueError(f'{draft.draft_id} approved action text was altered')
        imported_draft = draft.model_copy(update={
            'draft_status': RevisionDraftStatus.AWAITING_TEXT_APPROVAL,
            'updated_at': datetime.now(UTC),
        })
        imported_entries.append({
            'action_id': draft.action_id,
            'exact_reviewer_comments': entry['exact_reviewer_comments'],
            'approved_action_text': entry['approved_action_text'],
            'draft': imported_draft.model_dump(mode='json'),
        })

    missing = sorted(prepared_ids - seen_drafts)
    if missing:
        raise ValueError('missing completed revision drafts: ' + ', '.join(missing))
    imported_at = datetime.now(UTC)
    imported_payload = {
        'schema_version': 1,
        'imported_at': imported_at.isoformat(),
        'source_file_sha256': sha256_file(source),
        'source_document_hash': source_hash,
        'drafts': imported_entries,
        'approval_inferred': False,
    }
    report = {
        'schema_version': 1,
        'imported_at': imported_at.isoformat(),
        'draft_count': len(imported_entries),
        'draft_status_counts': dict(Counter(
            item['draft']['draft_status'] for item in imported_entries
        )),
        'source_file_sha256': sha256_file(source),
        'manuscript_modified': False,
    }
    return imported_payload, report
