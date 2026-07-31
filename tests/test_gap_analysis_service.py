import json
from pathlib import Path

import pytest

from scholarly_revision.models.enums import ReviewerSource
from scholarly_revision.models.reviewer import ReviewerComment
from scholarly_revision.services.gap_analysis_service import import_gap_analysis


def source_comment() -> ReviewerComment:
    return ReviewerComment(comment_id='R1-C01', reviewer_source=ReviewerSource.REVIEWER,
        reviewer_number=1, sequence_number=1, original_comment='Exact synthetic comment.')


def complete() -> dict:
    return {'comment_id': 'R1-C01', 'original_comment': 'Exact synthetic comment.',
        'coverage_status': 'NOT_ADDRESSED', 'interpretation': 'Author-supplied.',
        'manuscript_evidence': [], 'missing_elements': ['Synthetic detail absent.'],
        'required_actions': ['Add supported clarification.'], 'target_sections': ['Introduction'],
        'target_objects': [], 'required_references': [], 'required_experiments': [],
        'required_statistics': [], 'author_decision_required': True,
        'shared_with_comments': [], 'risks': [], 'confidence': 0.8,
        'manual_review_required': False, 'verification_status': None,
        'experiment_completion_claimed': False, 'experiment_evidence_ids': [],
        'verified_locations': [], 'action_proposals': []}


def write(tmp_path: Path, assessments: list[dict]) -> Path:
    path = tmp_path / 'analysis.json'
    path.write_text(json.dumps({'assessments': assessments}), encoding='utf-8')
    return path


def test_exact_comment_and_import_metadata(tmp_path: Path) -> None:
    imported = import_gap_analysis(write(tmp_path, [complete()]), [source_comment()])
    assert imported.assessments[0].original_comment == source_comment().original_comment
    assert imported.imported_payload['import_metadata']['author_fields_preserved']


def test_unknown_missing_and_changed_comments_rejected(tmp_path: Path) -> None:
    unknown = complete(); unknown['comment_id'] = 'R2-C01'
    with pytest.raises(ValueError, match='unknown comment'):
        import_gap_analysis(write(tmp_path, [unknown]), [source_comment()])
    with pytest.raises(ValueError, match='missing assessments'):
        import_gap_analysis(write(tmp_path, []), [source_comment()])
    changed = complete(); changed['original_comment'] = 'Changed.'
    with pytest.raises(ValueError, match='exact reviewer'):
        import_gap_analysis(write(tmp_path, [changed]), [source_comment()])


def test_unsupported_completion_claims_and_locations_rejected(tmp_path: Path) -> None:
    fully = complete(); fully['coverage_status'] = 'FULLY_ADDRESSED'
    with pytest.raises(ValueError, match='without manuscript evidence'):
        import_gap_analysis(write(tmp_path, [fully]), [source_comment()])
    experiment = complete(); experiment['experiment_completion_claimed'] = True
    with pytest.raises(ValueError, match='without evidence IDs'):
        import_gap_analysis(write(tmp_path, [experiment]), [source_comment()])
    location = complete(); location['target_sections'] = ['Page 4']
    with pytest.raises(ValueError, match='unverified absolute'):
        import_gap_analysis(write(tmp_path, [location]), [source_comment()])


def test_unsupported_coverage_rejected(tmp_path: Path) -> None:
    raw = complete(); raw['coverage_status'] = 'MAYBE'
    with pytest.raises(ValueError):
        import_gap_analysis(write(tmp_path, [raw]), [source_comment()])
