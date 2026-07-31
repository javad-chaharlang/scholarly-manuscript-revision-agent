from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarly_revision.models.enums import (
    ApprovalState,
    ChangeType,
    EvidenceStatus,
    HighlightColor,
    ReviewerSource,
    RevisionStatus,
)
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction


def comment_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        'comment_id': 'R1-C01',
        'reviewer_source': ReviewerSource.REVIEWER,
        'reviewer_number': 1,
        'sequence_number': 1,
        'original_comment': 'Please clarify the synthetic example.',
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize('comment_id', ['R1-C01', 'R2-C03', 'ED-C01', 'GEN-C01'])
def test_valid_comment_ids(comment_id: str) -> None:
    prefix, sequence = comment_id.split('-C')
    if prefix.startswith('R'):
        source = ReviewerSource.REVIEWER
        reviewer_number = int(prefix[1:])
    elif prefix == 'ED':
        source = ReviewerSource.EDITOR
        reviewer_number = None
    else:
        source = ReviewerSource.GENERAL
        reviewer_number = None
    comment = ReviewerComment.model_validate(
        comment_data(
            comment_id=comment_id,
            reviewer_source=source,
            reviewer_number=reviewer_number,
            sequence_number=int(sequence),
        )
    )
    assert comment.comment_id == comment_id


@pytest.mark.parametrize(
    'comment_id', ['R1-01', 'R0-C01', 'R1-C1', 'ED-01', 'GEN-CXX', 'R1-C01-extra']
)
def test_invalid_comment_ids_are_rejected(comment_id: str) -> None:
    with pytest.raises(ValidationError, match='comment ID'):
        ReviewerComment.model_validate(comment_data(comment_id=comment_id))


def test_automatic_reviewer_highlights() -> None:
    reviewer_1 = ReviewerComment.model_validate(comment_data())
    reviewer_2 = ReviewerComment.model_validate(
        comment_data(
            comment_id='R2-C01',
            reviewer_number=2,
            reviewer_source=ReviewerSource.REVIEWER,
        )
    )
    assert reviewer_1.highlight is HighlightColor.YELLOW
    assert reviewer_2.highlight is HighlightColor.BRIGHT_GREEN


def test_conflicting_highlight_is_rejected() -> None:
    with pytest.raises(ValidationError, match='conflicts'):
        ReviewerComment.model_validate(
            comment_data(highlight=HighlightColor.BRIGHT_GREEN)
        )


@pytest.mark.parametrize(
    ('source', 'comment_id'),
    [
        (ReviewerSource.EDITOR, 'ED-C01'),
        (ReviewerSource.GENERAL, 'GEN-C01'),
    ],
)
def test_editor_and_general_comments_are_violet(
    source: ReviewerSource, comment_id: str
) -> None:
    comment = ReviewerComment.model_validate(
        comment_data(
            comment_id=comment_id,
            reviewer_source=source,
            reviewer_number=None,
        )
    )
    assert comment.highlight is HighlightColor.VIOLET


def test_explicitly_shared_comment_is_violet() -> None:
    comment = ReviewerComment.model_validate(
        comment_data(shared_with=['R2-C01'])
    )
    assert comment.highlight is HighlightColor.VIOLET


def test_original_and_normalized_comment_stay_distinct() -> None:
    with pytest.raises(ValidationError, match='remain distinct'):
        ReviewerComment.model_validate(
            comment_data(
                normalized_comment='Please clarify the synthetic example.'
            )
        )


def action_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        'action_id': 'A-001',
        'comment_ids': ['R1-C01'],
        'change_type': ChangeType.REWRITE,
        'target_section': 'Methods',
        'rationale': 'Clarifies the anonymous synthetic description.',
        'approval_state': ApprovalState.APPROVED,
    }
    data.update(overrides)
    return data


def test_applied_action_requires_location() -> None:
    with pytest.raises(ValidationError, match='applied_location'):
        RevisionAction.model_validate(
            action_data(status=RevisionStatus.APPLIED)
        )


def test_verified_action_requires_verifier_and_time() -> None:
    with pytest.raises(ValidationError, match='verified_by'):
        RevisionAction.model_validate(
            action_data(
                status=RevisionStatus.VERIFIED,
                applied_location='verified synthetic section',
            )
        )
    with pytest.raises(ValidationError, match='verified_at'):
        RevisionAction.model_validate(
            action_data(
                status=RevisionStatus.VERIFIED,
                applied_location='verified synthetic section',
                verified_by='anonymous-verifier',
            )
        )


def test_verified_action_with_complete_verification_is_valid() -> None:
    action = RevisionAction.model_validate(
        action_data(
            status=RevisionStatus.VERIFIED,
            applied_location='verified synthetic section',
            verified_by='anonymous-verifier',
            verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    assert action.status is RevisionStatus.VERIFIED


def test_verified_comment_rejects_missing_or_unverified_evidence() -> None:
    for status in (
        EvidenceStatus.REQUIRED,
        EvidenceStatus.MISSING,
        EvidenceStatus.PROVIDED,
        EvidenceStatus.REJECTED,
    ):
        with pytest.raises(ValidationError, match='unverified evidence'):
            ReviewerComment.model_validate(
                comment_data(
                    status=RevisionStatus.VERIFIED,
                    evidence_status=status,
                )
            )
