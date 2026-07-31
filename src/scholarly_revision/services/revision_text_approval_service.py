'''Second explicit human approval gate for exact revision text.'''

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from scholarly_revision.models.enums import (
    RevisionDraftStatus,
    RevisionTextApprovalState,
    RevisionTextDecision,
)
from scholarly_revision.models.revision_draft import (
    RevisionDraft,
    RevisionTextDecisionRecord,
)


def revision_text_decision_template(drafts_payload: dict[str, Any]) -> dict[str, Any]:
    drafts = _drafts(drafts_payload)
    return {
        'schema_version': 1,
        'instructions': (
            'Record one explicit decision per draft. Blank decisions are not approvals. '
            'For APPROVE_TEXT, copy proposed_text exactly into approved_text.'
        ),
        'decisions': [
            {
                'draft_id': draft.draft_id,
                'decision': None,
                'decision_maker': None,
                'decision_timestamp': None,
                'approved_text': None,
                'author_modified_text': None,
                'author_note': None,
                'evidence_request': None,
                'rewrite_instruction': None,
                'unresolved_questions': [],
            }
            for draft in drafts
        ],
    }


def _drafts(payload: dict[str, Any]) -> list[RevisionDraft]:
    raw = payload.get('drafts')
    if not isinstance(raw, list):
        raise ValueError('revision_drafts.json must contain a drafts list')
    drafts: list[RevisionDraft] = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get('draft'), dict):
            raise ValueError('revision draft entry is malformed')
        drafts.append(RevisionDraft.model_validate(entry['draft']))
    return drafts


def _decision_updates(
    draft: RevisionDraft,
    record: RevisionTextDecisionRecord,
) -> dict[str, Any]:
    if record.decision is RevisionTextDecision.APPROVE_TEXT:
        if record.approved_text != draft.proposed_text:
            raise ValueError(
                f'{draft.draft_id} APPROVE_TEXT approved_text must match proposed_text exactly'
            )
        status = RevisionDraftStatus.APPROVED
        approval = RevisionTextApprovalState.APPROVED
        approved_text = draft.proposed_text
    elif record.decision is RevisionTextDecision.APPROVE_TEXT_WITH_MODIFICATION:
        status = RevisionDraftStatus.APPROVED
        approval = RevisionTextApprovalState.APPROVED
        approved_text = record.author_modified_text
    elif record.decision is RevisionTextDecision.REJECT_TEXT:
        status = RevisionDraftStatus.REJECTED
        approval = RevisionTextApprovalState.REJECTED
        approved_text = None
    elif record.decision is RevisionTextDecision.REQUEST_REWRITE:
        status = RevisionDraftStatus.REWRITE_REQUESTED
        approval = RevisionTextApprovalState.REVISION_REQUESTED
        approved_text = None
    elif record.decision is RevisionTextDecision.NEED_MORE_EVIDENCE:
        status = RevisionDraftStatus.NEED_MORE_EVIDENCE
        approval = RevisionTextApprovalState.NEEDS_EVIDENCE
        approved_text = None
    else:
        status = RevisionDraftStatus.DEFERRED
        approval = RevisionTextApprovalState.DEFERRED
        approved_text = None
    return {
        'draft_status': status,
        'approval_state': approval,
        'author_decision': record.decision,
        'author_modified_text': record.author_modified_text,
        'author_note': record.author_note,
        'approved_text': approved_text,
        'decision_maker': record.decision_maker,
        'decision_timestamp': record.decision_timestamp,
        'evidence_request': record.evidence_request,
        'rewrite_instruction': record.rewrite_instruction,
        'unresolved_questions': list(dict.fromkeys(
            [*draft.unresolved_questions, *record.unresolved_questions]
        )),
        'updated_at': record.decision_timestamp,
    }


def record_revision_text_decision(
    drafts_payload: dict[str, Any],
    record: RevisionTextDecisionRecord | dict[str, Any],
) -> dict[str, Any]:
    '''Return a payload with one explicit decision recorded; never infer approval.'''

    decision = RevisionTextDecisionRecord.model_validate(record)
    raw_entries = drafts_payload.get('drafts')
    if not isinstance(raw_entries, list):
        raise ValueError('revision_drafts.json must contain a drafts list')
    found = False
    updated_entries: list[dict[str, Any]] = []
    for entry in raw_entries:
        draft = RevisionDraft.model_validate(entry['draft'])
        if draft.draft_id != decision.draft_id:
            updated_entries.append(entry)
            continue
        found = True
        updated = draft.model_copy(update=_decision_updates(draft, decision))
        updated_entry = dict(entry)
        updated_entry['draft'] = updated.model_dump(mode='json')
        updated_entries.append(updated_entry)
    if not found:
        raise ValueError(f'unknown draft ID: {decision.draft_id}')
    result = dict(drafts_payload)
    result['drafts'] = updated_entries
    result['last_text_decision_at'] = decision.decision_timestamp.isoformat()
    result['approval_inferred'] = False
    result['text_approval_summary'] = revision_text_approval_summary(result)
    return result


def import_revision_text_decisions(
    drafts_payload: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = decisions_payload.get('decisions')
    if not isinstance(raw, list):
        raise ValueError('revision text decisions file must contain a decisions list')
    expected = {draft.draft_id for draft in _drafts(drafts_payload)}
    supplied = [
        item.get('draft_id') for item in raw if isinstance(item, dict)
    ]
    if len(supplied) != len(raw):
        raise ValueError('revision text decision entry is malformed')
    unknown = sorted(set(supplied) - expected)
    missing = sorted(expected - set(supplied))
    if unknown:
        raise ValueError('unknown draft IDs in decisions: ' + ', '.join(unknown))
    if missing:
        raise ValueError('missing decisions for draft IDs: ' + ', '.join(missing))
    if len(supplied) != len(set(supplied)):
        raise ValueError('duplicate draft decisions are not permitted')

    result = drafts_payload
    records: list[RevisionTextDecisionRecord] = []
    for item in raw:
        record = RevisionTextDecisionRecord.model_validate(item)
        result = record_revision_text_decision(result, record)
        records.append(record)
    audit = {
        'schema_version': 1,
        'imported_at': datetime.now(UTC).isoformat(),
        'decision_count': len(records),
        'decision_counts': dict(sorted(Counter(
            record.decision.value for record in records
        ).items())),
        'approval_inferred': False,
    }
    return result, audit


def revision_text_approval_summary(payload: dict[str, Any]) -> dict[str, int]:
    counts = Counter(draft.author_decision.value if draft.author_decision else 'PENDING'
                     for draft in _drafts(payload))
    return dict(sorted(counts.items()))
