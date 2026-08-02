from scholarly_revision.models.enums import (
    ChangeType,
    CommentCategory,
    HighlightColor,
    RevisionStatus,
)


def test_revision_status_values_are_exact() -> None:
    assert [status.value for status in RevisionStatus] == [
        'NOT_STARTED',
        'ANALYZED',
        'PLANNED',
        'DRAFTED',
        'APPLIED',
        'VERIFIED',
        'DEFERRED',
        'NOT_APPLICABLE',
    ]


def test_highlight_values_are_exact() -> None:
    assert {color.value for color in HighlightColor} == {
        'YELLOW',
        'BRIGHT_GREEN',
        'VIOLET',
        'LIGHT_BLUE',
        'PINK',
        'TEAL',
        'DARK_YELLOW',
        'GRAY_25',
        'DARK_BLUE',
        'RED',
    }


def test_required_categories_and_change_types_exist() -> None:
    assert CommentCategory.STATISTICS.value == 'STATISTICS'
    assert CommentCategory.STEGANALYSIS.value == 'STEGANALYSIS'
    assert ChangeType.EXPERIMENTAL_ADDITION.value == 'EXPERIMENTAL_ADDITION'
    assert ChangeType.GENERAL_CORRECTION.value == 'GENERAL_CORRECTION'
