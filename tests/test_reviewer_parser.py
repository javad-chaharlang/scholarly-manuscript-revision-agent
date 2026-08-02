from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarly_revision.models.enums import HighlightColor
from scholarly_revision.models.reviewer import ReviewerComment
from scholarly_revision.tools.docx_reader import DocxRecord, read_docx
from scholarly_revision.tools.reviewer_parser import parse_reviewer_comments


FIXTURE = Path(__file__).parent / 'fixtures' / 'synthetic_reviewer_comments.docx'


def parsed_comments() -> tuple[ReviewerComment, ...]:
    return parse_reviewer_comments(read_docx(FIXTURE)).comments


def test_heading_detection_and_stable_ids() -> None:
    comments = parsed_comments()
    assert [comment.comment_id for comment in comments] == [
        'ED-C01', 'R1-C01', 'R1-C02', 'R2-C01', 'R2-C02',
        'GEN-C01', 'GEN-C02',
    ]


def test_exact_original_text_and_normalized_text_are_separate() -> None:
    comment = next(item for item in parsed_comments() if item.comment_id == 'R1-C01')
    assert comment.original_comment == 'Please clarify the placeholder description.'
    assert comment.normalized_comment is None
    records = [
        DocxRecord(0, 'paragraph', 'Reviewer 1', 'Heading 1'),
        DocxRecord(1, 'paragraph', 'Comment 1', 'Normal'),
        DocxRecord(2, 'paragraph', 'Keep   exact\nline spacing.', 'Normal'),
    ]
    normalized = parse_reviewer_comments(records).comments[0]
    assert normalized.original_comment == 'Keep   exact\nline spacing.'
    assert normalized.normalized_comment == 'Keep exact line spacing.'


def test_highlight_assignment_and_ambiguous_flagging() -> None:
    comments = {comment.comment_id: comment for comment in parsed_comments()}
    assert comments['R1-C01'].highlight is HighlightColor.YELLOW
    assert comments['R2-C01'].highlight is HighlightColor.BRIGHT_GREEN
    assert comments['ED-C01'].highlight is HighlightColor.VIOLET
    assert comments['GEN-C01'].highlight is HighlightColor.VIOLET
    assert comments['GEN-C02'].manual_review_required is True
    assert sum(comment.manual_review_required for comment in comments.values()) == 1


def test_incorrect_highlight_is_rejected_by_existing_model() -> None:
    with pytest.raises(ValidationError, match='conflicts'):
        ReviewerComment(
            comment_id='R1-C01',
            reviewer_source='REVIEWER',
            reviewer_number=1,
            sequence_number=1,
            original_comment='Anonymous synthetic comment.',
            highlight='VIOLET',
        )


def test_explicit_combined_heading_is_not_merged() -> None:
    records = [
        DocxRecord(0, 'paragraph', 'Reviewer 1, Comment 3', 'Normal'),
        DocxRecord(1, 'paragraph', 'First exact block.', 'Normal'),
        DocxRecord(2, 'paragraph', 'Reviewer 1, Comment 4: Second exact block.', 'Normal'),
    ]
    comments = parse_reviewer_comments(records).comments
    assert [comment.comment_id for comment in comments] == ['R1-C03', 'R1-C04']
    assert [comment.original_comment for comment in comments] == [
        'First exact block.', 'Second exact block.'
    ]


def test_third_reviewer_is_parsed_without_a_fixed_reviewer_limit() -> None:
    records = [
        DocxRecord(0, 'paragraph', 'Reviewer 3', 'Heading 1'),
        DocxRecord(1, 'paragraph', 'Comment 1: Add a limitation.', 'Normal'),
    ]
    comment = parse_reviewer_comments(records).comments[0]
    assert comment.comment_id == 'R3-C01'
    assert comment.reviewer_number == 3
    assert comment.highlight is HighlightColor.LIGHT_BLUE
