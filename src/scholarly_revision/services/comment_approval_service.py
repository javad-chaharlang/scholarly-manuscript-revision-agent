'''Build and enforce the HybridQDL-style comment-centric approval gate.'''

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from scholarly_revision.models.comment_approval import (
    CommentApprovalBundle,
    CommentApprovalDecision,
    CommentApprovalRecord,
)
from scholarly_revision.models.reviewer import ReviewerComment
from scholarly_revision.models.revision_draft import RevisionDraft
from scholarly_revision.services.gap_analysis_service import read_json, write_json


APPROVAL_TEMPLATE = 'comment_approval_template.json'
APPROVAL_WORKING = 'comment_approval_working.json'
APPROVAL_PACKET = 'comment_approval_packet.json'


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def draft_fingerprint(draft: RevisionDraft) -> str:
    '''Bind approval to the complete normalized draft, not only its identifier.'''

    serialized = json.dumps(
        draft.model_dump(mode='json'), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'),
    )
    return _sha256_text(serialized)


def _draft_entries(drafts_payload: dict[str, Any]) -> list[tuple[dict[str, Any], RevisionDraft]]:
    raw = drafts_payload.get('drafts')
    if not isinstance(raw, list) or not raw:
        raise ValueError('revision_drafts.json must contain a non-empty drafts list')
    result = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get('draft'), dict):
            raise ValueError('revision draft entry is malformed')
        result.append((entry, RevisionDraft.model_validate(entry['draft'])))
    return result


def build_comment_approval_template(
    drafts_payload: dict[str, Any],
    comments: Iterable[ReviewerComment | dict[str, Any]],
) -> dict[str, Any]:
    '''Create one review packet for every exact reviewer/editor/general comment.'''

    entries = _draft_entries(drafts_payload)
    validated_comments = [ReviewerComment.model_validate(item) for item in comments]
    if not validated_comments:
        raise ValueError('comment approval requires at least one reviewer comment')
    comment_map = {item.comment_id: item for item in validated_comments}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_hashes: set[str] = set()
    for entry, draft in entries:
        source_hashes.add(draft.source_document_hash)
        exact_items = entry.get('exact_reviewer_comments')
        if not isinstance(exact_items, list):
            raise ValueError('draft entry lacks exact_reviewer_comments')
        exact_map = {
            str(item['comment_id']): str(item['exact_comment'])
            for item in exact_items
        }
        for comment_id in draft.comment_ids:
            comment = comment_map.get(comment_id)
            if comment is None:
                raise ValueError(f'{draft.draft_id} references unknown comment {comment_id}')
            if exact_map.get(comment_id) != comment.original_comment:
                raise ValueError(f'exact reviewer comment changed for {comment_id}')
            grouped[comment_id].append({
                'draft_id': draft.draft_id,
                'action_id': draft.action_id,
                'target_section': draft.target_section,
                'target_element_ids': draft.target_element_ids,
                'operation': draft.operation.value,
                'original_text_snapshot': draft.original_text_snapshot,
                'approved_manuscript_text': draft.text_for_application,
                'text_approval_state': draft.approval_state.value,
                'manual_handling_required': draft.manual_handling_required,
                'highlight': draft.highlight.value,
                'draft_sha256': draft_fingerprint(draft),
            })
    if len(source_hashes) != 1:
        raise ValueError('all drafts must share one source document hash')
    source_hash = next(iter(source_hashes))
    records = []
    for number, comment in enumerate(validated_comments, start=1):
        changes = grouped.get(comment.comment_id, [])
        records.append({
            'approval_id': f'CAP-{number:04d}',
            'comment_id': comment.comment_id,
            'exact_comment': comment.original_comment,
            'exact_comment_sha256': _sha256_text(comment.original_comment),
            'source_document_hash': source_hash,
            'related_draft_ids': [item['draft_id'] for item in changes],
            'related_draft_hashes': {
                item['draft_id']: item['draft_sha256'] for item in changes
            },
            'proposed_changes': changes,
            'proposed_response': '',
            'decision': None,
            'approved_response': None,
            'author_modified_response': None,
            'approved_draft_ids': [],
            'decision_maker': None,
            'decision_timestamp': None,
            'author_note': None,
            'evidence_request': None,
            'rewrite_instruction': None,
        })
    return {
        'schema_version': 1,
        'source_document_hash': source_hash,
        'instructions': (
            'Review each exact comment, proposed response, and every linked manuscript '
            'change together. Edit as needed and record an explicit researcher decision. '
            'No manuscript mutation may precede completion of this gate.'
        ),
        'records': records,
    }


def validate_comment_approval_bundle(payload: dict[str, Any]) -> CommentApprovalBundle:
    '''Validate completed decisions while checking display-only exact comment text.'''

    raw_records = payload.get('records')
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError('comment approval packet must contain records')
    records = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError('comment approval record is malformed')
        item = dict(raw)
        exact_comment = item.pop('exact_comment', None)
        item.pop('proposed_changes', None)
        if exact_comment is not None and _sha256_text(str(exact_comment)) != item.get(
            'exact_comment_sha256'
        ):
            raise ValueError(f"exact reviewer comment changed for {item.get('comment_id')}")
        records.append(item)
    return CommentApprovalBundle.model_validate({
        'schema_version': payload.get('schema_version', 1),
        'source_document_hash': payload.get('source_document_hash'),
        'records': records,
    })


def prepare_comment_approval(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    drafts = read_json(root / 'working' / 'revision_drafts.json')
    comments = read_json(root / 'working' / 'reviewer_comments.json')
    template = build_comment_approval_template(drafts, comments)
    template_path = write_json(root / 'working' / APPROVAL_TEMPLATE, template)
    write_json(root / 'working' / APPROVAL_WORKING, template)
    return template_path


def invalidate_comment_approval(project_root: str | Path) -> None:
    root = Path(project_root).expanduser().resolve()
    for name in (APPROVAL_TEMPLATE, APPROVAL_WORKING, APPROVAL_PACKET):
        (root / 'working' / name).unlink(missing_ok=True)


def record_comment_approval_decision(
    project_root: str | Path,
    *,
    comment_id: str,
    proposed_response: str,
    decision: CommentApprovalDecision | str,
    decision_maker: str,
    approved_draft_ids: list[str] | None = None,
    author_modified_response: str | None = None,
    author_note: str | None = None,
    evidence_request: str | None = None,
    rewrite_instruction: str | None = None,
) -> tuple[dict[str, Any], CommentApprovalBundle | None]:
    '''Persist one decision and finalize the mandatory packet when coverage is complete.'''

    root = Path(project_root).expanduser().resolve()
    working_path = root / 'working' / APPROVAL_WORKING
    if not working_path.is_file():
        prepare_comment_approval(root)
    payload = read_json(working_path)
    records = payload.get('records', [])
    target = next(
        (item for item in records if item.get('comment_id') == comment_id),
        None,
    )
    if target is None:
        raise ValueError(f'unknown comment approval record: {comment_id}')
    selected = CommentApprovalDecision(decision)
    approved_response = None
    selected_drafts = list(approved_draft_ids or [])
    text_eligible = {
        str(item.get('draft_id'))
        for item in target.get('proposed_changes', [])
        if item.get('text_approval_state') == 'APPROVED'
        and not item.get('manual_handling_required')
    }
    if set(selected_drafts) - text_eligible:
        raise ValueError(
            'comment-package approval may authorize only exact-text-approved, '
            'non-manual linked drafts'
        )
    if selected is CommentApprovalDecision.APPROVE_PACKAGE:
        approved_response = proposed_response
    elif selected is CommentApprovalDecision.APPROVE_WITH_MODIFICATION:
        approved_response = author_modified_response
    else:
        selected_drafts = []
    record = CommentApprovalRecord(
        approval_id=str(target['approval_id']),
        comment_id=comment_id,
        exact_comment_sha256=str(target['exact_comment_sha256']),
        source_document_hash=str(payload['source_document_hash']),
        related_draft_ids=list(target.get('related_draft_ids', [])),
        related_draft_hashes=dict(target.get('related_draft_hashes', {})),
        proposed_response=proposed_response,
        approved_response=approved_response,
        author_modified_response=author_modified_response,
        approved_draft_ids=selected_drafts,
        decision=selected,
        decision_maker=decision_maker,
        decision_timestamp=datetime.now(UTC),
        author_note=author_note,
        evidence_request=evidence_request,
        rewrite_instruction=rewrite_instruction,
    )
    replacement = {
        **target,
        **record.model_dump(mode='json'),
    }
    payload['records'] = [
        replacement if item.get('comment_id') == comment_id else item
        for item in records
    ]
    write_json(working_path, payload)

    history_path = root / 'audit' / 'comment_approval_history.json'
    history = read_json(history_path) if history_path.is_file() else {
        'schema_version': 1,
        'decisions': [],
        'approval_inferred': False,
    }
    history['decisions'].append(record.model_dump(mode='json'))
    write_json(history_path, history)

    if not all(item.get('decision') for item in payload['records']):
        return payload, None
    bundle = validate_comment_approval_bundle(payload)
    write_json(
        root / 'working' / APPROVAL_PACKET,
        bundle.model_dump(mode='json'),
    )
    write_json(root / 'audit' / 'comment_approval_completion.json', {
        'schema_version': 1,
        'completed_at': datetime.now(UTC).isoformat(),
        'record_count': len(bundle.records),
        'approved_comment_count': len(bundle.approved_comment_ids),
        'approved_draft_count': len(bundle.approved_draft_ids),
        'approval_inferred': False,
    })
    return payload, bundle


def eligible_draft_ids(
    bundle: CommentApprovalBundle,
    drafts: list[RevisionDraft],
) -> set[str]:
    '''Return drafts approved by every reviewer comment linked to that draft.'''

    approved_comments = bundle.approved_comment_ids
    records_by_comment = {record.comment_id: record for record in bundle.records}
    return {
        draft.draft_id
        for draft in drafts
        if set(draft.comment_ids).issubset(approved_comments)
        and all(
            comment_id in records_by_comment
            and draft.draft_id in records_by_comment[comment_id].approved_draft_ids
            and records_by_comment[comment_id].related_draft_hashes.get(draft.draft_id)
            == draft_fingerprint(draft)
            for comment_id in draft.comment_ids
        )
        and draft.source_document_hash == bundle.source_document_hash
    }


def changed_approved_draft_ids(
    bundle: CommentApprovalBundle,
    drafts: list[RevisionDraft],
) -> set[str]:
    '''Detect approved draft records changed or removed after researcher approval.'''

    current = {draft.draft_id: draft for draft in drafts}
    changed: set[str] = set()
    for record in bundle.records:
        for draft_id in record.approved_draft_ids:
            draft = current.get(draft_id)
            if (
                draft is None
                or record.related_draft_hashes.get(draft_id)
                != draft_fingerprint(draft)
            ):
                changed.add(draft_id)
    return changed


def approved_response_map(project_root: str | Path) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    path = root / 'working' / APPROVAL_PACKET
    if not path.is_file():
        return {}
    bundle = validate_comment_approval_bundle(read_json(path))
    return {
        record.comment_id: record.approved_response
        for record in bundle.records
        if record.approved_response is not None
    }
