from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarly_revision.models.response_package import ResponseEntry, ResponsePackage


def entry(**updates):
    data = {
        'response_entry_id': 'RESP-0001', 'reviewer_source': 'REVIEWER',
        'reviewer_number': 1, 'comment_id': 'R1-C01', 'sequence_number': 1,
        'exact_comment': 'Exact anonymous comment.', 'author_response': 'Response.',
        'highlight': 'YELLOW', 'response_status': 'APPROVED',
        'location_status': 'NOT_REQUIRED', 'evidence_status': 'NOT_REQUIRED',
        'author_approved': True, 'resolution': 'NOT_APPLICABLE',
    }
    data.update(updates)
    return ResponseEntry.model_validate(data)


def test_rejected_request_requires_author_approved_justification() -> None:
    with pytest.raises(ValidationError, match='justification'):
        entry(resolution='RESPECTFULLY_DECLINED')
    assert entry(
        resolution='RESPECTFULLY_DECLINED',
        author_justification='Anonymous author-approved reason.',
    ).author_approved


def test_deferred_action_must_remain_explicit() -> None:
    with pytest.raises(ValidationError, match='unresolved limitations'):
        entry(resolution='DEFERRED')
    assert entry(
        resolution='DEFERRED', unresolved_limitations=['Deferred with reason.']
    ).resolution.value == 'DEFERRED'


def test_duplicate_response_comment_is_rejected() -> None:
    package = {
        'generated_at': datetime.now(UTC), 'manuscript_title': 'Synthetic',
        'manuscript_id': 'SYN', 'journal': 'Synthetic', 'revision_round': 1,
        'cover_letter': {}, 'sections': [{
            'section_id': 'S1', 'title': 'Reviewer 1',
            'reviewer_source': 'REVIEWER', 'reviewer_number': 1,
            'entries': [entry(), entry(response_entry_id='RESP-0002')],
        }], 'closing_statement': 'Closing.'
    }
    with pytest.raises(ValidationError, match='duplicate response entries'):
        ResponsePackage.model_validate(package)


def test_response_entry_template_is_valid_json() -> None:
    path = Path(__file__).resolve().parents[1] / 'templates' / 'response_entry_template.json'
    assert json.loads(path.read_text(encoding='utf-8'))['comment_id'] == 'R1-C01'
