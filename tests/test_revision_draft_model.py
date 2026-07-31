from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarly_revision.models.revision_draft import RevisionDraft


def draft_data(**updates):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    data = {
        'draft_id': 'DRAFT-0001',
        'action_id': 'ACT-0001',
        'comment_ids': ['R1-C01'],
        'source_document_hash': '0' * 64,
        'target_element_ids': ['PAR-0001'],
        'target_section': 'Introduction',
        'operation': 'REPLACE_PARAGRAPH',
        'original_text_snapshot': 'Synthetic original.',
        'original_text_hash': '1' * 64,
        'proposed_text': 'Synthetic replacement.',
        'drafting_rationale': 'Anonymous rationale.',
        'highlight': 'YELLOW',
        'draft_status': 'DRAFTED',
        'created_at': now,
        'updated_at': now,
    }
    data.update(updates)
    return data


def test_draft_action_traceability_and_applied_gate() -> None:
    draft = RevisionDraft.model_validate(draft_data())
    assert draft.action_id == 'ACT-0001'
    with pytest.raises(ValidationError, match='exact-text approval'):
        RevisionDraft.model_validate(draft_data(draft_status='APPLIED'))


def test_modified_approval_and_deletion_requirements() -> None:
    with pytest.raises(ValidationError, match='author_modified_text'):
        RevisionDraft.model_validate(draft_data(
            author_decision='APPROVE_TEXT_WITH_MODIFICATION',
            approval_state='APPROVED',
            approved_text='Modified.',
        ))
    with pytest.raises(ValidationError, match='deletion justification'):
        RevisionDraft.model_validate(draft_data(
            operation='DELETE_PARAGRAPH', proposed_text=''
        ))


def test_table_coordinates_and_claim_evidence_required() -> None:
    with pytest.raises(ValidationError, match='table ID'):
        RevisionDraft.model_validate(draft_data(operation='REPLACE_TABLE_CELL'))
    with pytest.raises(ValidationError, match='scientific claims'):
        RevisionDraft.model_validate(draft_data(scientific_claim_ids=['CLAIM-001']))
