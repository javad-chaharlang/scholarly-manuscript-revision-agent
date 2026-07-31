from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarly_revision.models.gap_analysis import ApprovalRecord
from scholarly_revision.services.approval_service import record_decision


def plan() -> dict:
    return {'approval_gate_status': 'READY_FOR_REVIEW', 'actions': [
        {'action_id': f'ACT-{n:04d}', 'comment_ids': ['R1-C01'],
         'change_type': 'ADDITION', 'target_section': 'Introduction',
         'proposed_revision_summary': 'Synthetic plan.', 'rationale': 'Synthetic.',
         'status': 'PLANNED', 'approval_state': 'PENDING'} for n in (1, 2)]}


def test_required_decision_fields() -> None:
    with pytest.raises(ValidationError, match='justification'):
        ApprovalRecord(decision='REJECT_WITH_JUSTIFICATION',
            decision_maker='author', decision_timestamp=datetime.now(UTC))
    with pytest.raises(ValidationError, match='revised action text'):
        ApprovalRecord(decision='APPROVE_WITH_MODIFICATION',
            decision_maker='author', decision_timestamp=datetime.now(UTC))


def test_approval_modification_evidence_and_defer() -> None:
    approved = record_decision(plan(), action_id='ACT-0001', decision='APPROVE',
        decision_maker='author')
    assert approved['approval_gate_status'] == 'PARTIALLY_APPROVED'
    modified = record_decision(approved, action_id='ACT-0002',
        decision='APPROVE_WITH_MODIFICATION', decision_maker='author',
        modified_action_text='Explicit revised action.')
    assert modified['approval_gate_status'] == 'APPROVED'
    evidence = record_decision(plan(), action_id='ACT-0001',
        decision='NEED_MORE_EVIDENCE', decision_maker='author',
        evidence_request='Provide evidence.')
    assert evidence['approval_gate_status'] == 'BLOCKED'
    deferred = record_decision(plan(), action_id='ACT-0001', decision='DEFER',
        decision_maker='author')
    assert deferred['actions'][0]['status'] == 'DEFERRED'
    assert deferred['actions'][0]['approval_state'] == 'PENDING'
