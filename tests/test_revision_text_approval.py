from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarly_revision.models.revision_draft import RevisionDraft, RevisionTextDecisionRecord
from scholarly_revision.services.revision_text_approval_service import (
    record_revision_text_decision,
)


def payload() -> dict:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    draft = RevisionDraft(
        draft_id='DRAFT-0001', action_id='ACT-0001', comment_ids=['R1-C01'],
        source_document_hash='0' * 64, target_element_ids=['PAR-0001'],
        target_section='Introduction', operation='REPLACE_PARAGRAPH',
        original_text_snapshot='Old.', original_text_hash='1' * 64,
        proposed_text='Exact proposed.', drafting_rationale='Synthetic.',
        highlight='YELLOW', draft_status='AWAITING_TEXT_APPROVAL',
        created_at=now, updated_at=now,
    )
    return {'drafts': [{'draft': draft.model_dump(mode='json')}]}


def test_exact_and_modified_approval() -> None:
    when = datetime(2026, 1, 2, tzinfo=UTC)
    with pytest.raises(ValueError, match='match proposed_text exactly'):
        record_revision_text_decision(payload(), {
            'draft_id': 'DRAFT-0001', 'decision': 'APPROVE_TEXT',
            'decision_maker': 'author', 'decision_timestamp': when,
            'approved_text': 'Changed.',
        })
    updated = record_revision_text_decision(payload(), {
        'draft_id': 'DRAFT-0001',
        'decision': 'APPROVE_TEXT_WITH_MODIFICATION',
        'decision_maker': 'author', 'decision_timestamp': when,
        'approved_text': 'Author exact modification.',
        'author_modified_text': 'Author exact modification.',
    })
    assert updated['drafts'][0]['draft']['approved_text'] == 'Author exact modification.'


def test_rejection_rewrite_and_evidence_fields_required() -> None:
    base = {'draft_id': 'DRAFT-0001', 'decision_maker': 'author',
            'decision_timestamp': datetime(2026, 1, 2, tzinfo=UTC)}
    with pytest.raises(ValidationError, match='justification'):
        RevisionTextDecisionRecord(**base, decision='REJECT_TEXT')
    with pytest.raises(ValidationError, match='rewrite_instruction'):
        RevisionTextDecisionRecord(**base, decision='REQUEST_REWRITE')
    with pytest.raises(ValidationError, match='evidence_request'):
        RevisionTextDecisionRecord(**base, decision='NEED_MORE_EVIDENCE')
