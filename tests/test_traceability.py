from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarly_revision.models.enums import (
    ApprovalState,
    ChangeType,
    EvidenceStatus,
    HighlightColor,
    ResultStatus,
    ReviewerSource,
    RevisionStatus,
)
from scholarly_revision.models.evidence import ExperimentalResultRecord
from scholarly_revision.models.reference import ReferenceRecord
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.traceability import (
    ResponseLetterEntry,
    TraceabilityRecord,
)


def test_final_result_requires_verified_source_evidence() -> None:
    with pytest.raises(ValidationError, match='VERIFIED source evidence'):
        ExperimentalResultRecord(
            result_id='RES-001',
            metric_name='synthetic metric',
            value=1,
            source_file='synthetic.csv',
            result_status=ResultStatus.FINAL,
            evidence_status=EvidenceStatus.PROVIDED,
        )
    with pytest.raises(ValidationError, match='source_file'):
        ExperimentalResultRecord(
            result_id='RES-001',
            metric_name='synthetic metric',
            value=1,
            result_status=ResultStatus.FINAL,
            evidence_status=EvidenceStatus.VERIFIED,
        )


def test_numeric_result_requires_metric_name() -> None:
    with pytest.raises(ValidationError, match='metric_name'):
        ExperimentalResultRecord(result_id='RES-001', value=1)


def test_verified_reference_requires_title_and_authors() -> None:
    with pytest.raises(ValidationError, match='title and authors'):
        ReferenceRecord(
            reference_id='REF-001',
            reason_added='Anonymous synthetic validation fixture.',
            requested_by_comment_ids=['R1-C01'],
            bibliographic_verified=True,
        )


def test_reference_highlight_defaults_and_conflicts() -> None:
    reviewer_2_reference = ReferenceRecord(
        reference_id='REF-002',
        reason_added='Anonymous synthetic validation fixture.',
        requested_by_comment_ids=['R2-C01'],
    )
    assert reviewer_2_reference.highlight is HighlightColor.BRIGHT_GREEN
    general_reference = ReferenceRecord(
        reference_id='REF-003',
        reason_added='General synthetic fixture.',
    )
    assert general_reference.highlight is HighlightColor.VIOLET
    with pytest.raises(ValidationError, match='conflicts'):
        ReferenceRecord(
            reference_id='REF-004',
            reason_added='Anonymous synthetic validation fixture.',
            requested_by_comment_ids=['R1-C01'],
            highlight=HighlightColor.VIOLET,
        )


def test_reference_final_number_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ReferenceRecord(
            reference_id='REF-005',
            final_number=0,
            reason_added='Anonymous synthetic validation fixture.',
        )


def test_verified_response_with_changes_requires_location() -> None:
    with pytest.raises(ValidationError, match='require a location'):
        ResponseLetterEntry(
            response_entry_id='RESP-001',
            comment_id='R1-C01',
            exact_comment='Please clarify the synthetic example.',
            author_response='The concern is addressed in the synthetic fixture.',
            changes_made='A clarification was applied and verified.',
            location=None,
            highlight=HighlightColor.YELLOW,
            verification_status=RevisionStatus.VERIFIED,
        )


def source_comment() -> ReviewerComment:
    return ReviewerComment(
        comment_id='R1-C01',
        reviewer_source=ReviewerSource.REVIEWER,
        reviewer_number=1,
        sequence_number=1,
        original_comment='Please clarify the synthetic example.',
    )


def response_entry() -> ResponseLetterEntry:
    return ResponseLetterEntry(
        response_entry_id='RESP-001',
        comment_id='R1-C01',
        exact_comment='Please clarify the synthetic example.',
        author_response='The concern is addressed in the synthetic fixture.',
        changes_made='A clarification was applied and verified.',
        location='verified synthetic section',
        highlight=HighlightColor.YELLOW,
        verification_status=RevisionStatus.VERIFIED,
    )


def test_response_change_requires_corresponding_verified_action() -> None:
    response = response_entry()
    with pytest.raises(ValueError, match='verified RevisionAction'):
        response.validate_against_source(source_comment(), [])
    unverified_action = RevisionAction(
        action_id='A-001',
        comment_ids=['R1-C01'],
        change_type=ChangeType.REWRITE,
        target_section='Methods',
        rationale='Synthetic clarification.',
        approval_state=ApprovalState.APPROVED,
        status=RevisionStatus.APPLIED,
        applied_location='verified synthetic section',
    )
    with pytest.raises(ValueError, match='verified RevisionAction'):
        response.validate_against_source(source_comment(), [unverified_action])


def test_response_accepts_corresponding_verified_action() -> None:
    action = RevisionAction(
        action_id='A-001',
        comment_ids=['R1-C01'],
        change_type=ChangeType.REWRITE,
        target_section='Methods',
        rationale='Synthetic clarification.',
        approval_state=ApprovalState.APPROVED,
        status=RevisionStatus.VERIFIED,
        applied_location='verified synthetic section',
        verified_by='anonymous-verifier',
        verified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    response_entry().validate_against_source(source_comment(), [action])


def test_exact_response_comment_must_match_source() -> None:
    response = response_entry().model_copy(
        update={'exact_comment': 'Paraphrased synthetic text.'}
    )
    with pytest.raises(ValueError, match='does not preserve'):
        response.validate_against_source(source_comment(), [])


def test_final_traceability_rejects_missing_mappings_and_issues() -> None:
    with pytest.raises(ValidationError, match='required_action_ids'):
        TraceabilityRecord(
            trace_id='TRACE-001',
            comment_id='R1-C01',
            interpretation_complete=True,
            manuscript_change_ids=['A-001'],
            response_entry_id='RESP-001',
            location_verified=True,
            highlight_verified=True,
            scientific_claims_verified=True,
            final_status=RevisionStatus.VERIFIED,
            author_approved=True,
            last_checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match='unresolved issues'):
        TraceabilityRecord(
            trace_id='TRACE-001',
            comment_id='R1-C01',
            interpretation_complete=True,
            required_action_ids=['A-001'],
            manuscript_change_ids=['A-001'],
            response_entry_id='RESP-001',
            location_verified=True,
            highlight_verified=True,
            scientific_claims_verified=True,
            final_status=RevisionStatus.VERIFIED,
            unresolved_issues=['Synthetic unresolved issue.'],
            author_approved=True,
            last_checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
