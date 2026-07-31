'''Explicit human approval decisions for Phase 4 revision actions.'''

from __future__ import annotations

from datetime import UTC, datetime

from scholarly_revision.models.enums import (
    ApprovalDecision,
    ApprovalGateStatus,
    ApprovalState,
    RevisionStatus,
)
from scholarly_revision.models.gap_analysis import ApprovalRecord
from scholarly_revision.models.reviewer import RevisionAction


def approval_gate_status(actions: list[RevisionAction]) -> ApprovalGateStatus:
    if not actions:
        return ApprovalGateStatus.NOT_READY
    decisions = {action.approval_decision for action in actions}
    if decisions == {None}:
        return ApprovalGateStatus.READY_FOR_REVIEW
    if any(
        decision == ApprovalDecision.NEED_MORE_EVIDENCE.value
        for decision in decisions
    ):
        return ApprovalGateStatus.BLOCKED
    completed = {
        ApprovalDecision.APPROVE.value,
        ApprovalDecision.APPROVE_WITH_MODIFICATION.value,
        ApprovalDecision.REJECT_WITH_JUSTIFICATION.value,
    }
    if all(decision in completed for decision in decisions):
        return ApprovalGateStatus.APPROVED
    return ApprovalGateStatus.PARTIALLY_APPROVED


def record_decision(
    plan: dict[str, object],
    *,
    action_id: str,
    decision: ApprovalDecision | str,
    decision_maker: str,
    author_note: str | None = None,
    modified_action_text: str | None = None,
    evidence_request: str | None = None,
    unresolved_questions: list[str] | None = None,
    decision_timestamp: datetime | None = None,
) -> dict[str, object]:
    '''Return an updated plan; a decision is never inferred.'''

    timestamp = decision_timestamp or datetime.now(UTC)
    record = ApprovalRecord(
        decision=decision,
        author_note=author_note,
        modified_action_text=modified_action_text,
        evidence_request=evidence_request,
        decision_timestamp=timestamp,
        decision_maker=decision_maker,
        unresolved_questions=unresolved_questions or [],
    )
    raw_actions = plan.get('actions')
    if not isinstance(raw_actions, list):
        raise ValueError('revision plan has no actions list')
    updated: list[RevisionAction] = []
    found = False
    for raw_action in raw_actions:
        action = RevisionAction.model_validate(raw_action)
        if action.action_id != action_id:
            updated.append(action)
            continue
        found = True
        if record.decision in {
            ApprovalDecision.APPROVE,
            ApprovalDecision.APPROVE_WITH_MODIFICATION,
        }:
            approval_state = ApprovalState.APPROVED
            status = RevisionStatus.PLANNED
        elif record.decision is ApprovalDecision.REJECT_WITH_JUSTIFICATION:
            approval_state = ApprovalState.REJECTED
            status = RevisionStatus.NOT_APPLICABLE
        elif record.decision is ApprovalDecision.NEED_MORE_EVIDENCE:
            approval_state = ApprovalState.REVISION_REQUESTED
            status = RevisionStatus.PLANNED
        else:
            approval_state = ApprovalState.PENDING
            status = RevisionStatus.DEFERRED
        updated.append(action.model_copy(update={
            'approval_state': approval_state,
            'status': status,
            'approval_decision': record.decision.value,
            'author_note': record.author_note,
            'modified_action_text': record.modified_action_text,
            'evidence_request': record.evidence_request,
            'decision_timestamp': record.decision_timestamp,
            'decision_maker': record.decision_maker,
            'unresolved_questions': list(dict.fromkeys(
                [*action.unresolved_questions, *record.unresolved_questions]
            )),
        }))
    if not found:
        raise ValueError(f'unknown action ID: {action_id}')
    result = dict(plan)
    result['actions'] = [action.model_dump(mode='json') for action in updated]
    result['approval_gate_status'] = approval_gate_status(updated).value
    result['last_decision_at'] = timestamp.isoformat()
    return result


def decision_template(plan: dict[str, object]) -> dict[str, object]:
    return {
        'schema_version': 1,
        'instructions': 'Complete decisions explicitly; blank decisions are not approvals.',
        'decisions': [
            {
                'action_id': action['action_id'],
                'decision': None,
                'decision_maker': None,
                'author_note': None,
                'modified_action_text': None,
                'evidence_request': None,
                'unresolved_questions': [],
            }
            for action in plan.get('actions', [])
        ],
    }
