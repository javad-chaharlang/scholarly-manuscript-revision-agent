'''Prepare and strictly import source-grounded Phase 4 gap analyses.'''

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.enums import CoverageStatus, EvidenceStatus
from scholarly_revision.models.gap_analysis import GapAnalysisAssessment
from scholarly_revision.models.reviewer import ReviewerComment
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.tools.manuscript_structure_reader import ManuscriptStructure


_ABSOLUTE_LOCATION = re.compile(
    r'\b(?:page|pages|p\.|line|lines)\s*#?\s*\d+\b', re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class GapAnalysisImport:
    assessments: tuple[GapAnalysisAssessment, ...]
    imported_payload: dict[str, Any]
    source_hash: str
    imported_at: str
    coverage_counts: dict[str, int]


def read_json(path: str | Path) -> Any:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f'JSON file not found: {source}')
    try:
        return json.loads(source.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'invalid JSON file: {source}') from exc


def write_json(path: str | Path, payload: Any) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write('\n')
    return destination


def _comments(project_root: Path) -> list[ReviewerComment]:
    raw = read_json(project_root / 'working' / 'reviewer_comments.json')
    if not isinstance(raw, list):
        raise ValueError('reviewer_comments.json must contain a list')
    return [ReviewerComment.model_validate(item) for item in raw]


def build_gap_analysis_package(
    project_root: str | Path,
    structure: ManuscriptStructure,
    manuscript_file: str | Path,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
    comments = _comments(root)
    manuscript_path = Path(manuscript_file).expanduser().resolve()
    reviewer_payload = []
    assessments = []
    for comment in comments:
        reviewer_payload.append({
            'comment_id': comment.comment_id,
            'original_comment': comment.original_comment,
            'reviewer_source': comment.reviewer_source.value,
            'reviewer_number': comment.reviewer_number,
            'sequence_number': comment.sequence_number,
            'current_comment_status': comment.status.value,
            'current_evidence_status': comment.evidence_status.value,
            'highlight': comment.highlight.value,
            'manual_review_required': comment.manual_review_required,
        })
        assessments.append(
            GapAnalysisAssessment(
                comment_id=comment.comment_id,
                original_comment=comment.original_comment,
            ).model_dump(mode='json')
        )
    return {
        'schema_version': 1,
        'package_status': 'BLANK_SEMANTIC_ASSESSMENTS',
        'prepared_at': datetime.now(UTC).isoformat(),
        'project_metadata': {
            'project_name': manifest.project_name,
            'manuscript_id': manifest.manuscript_id,
            'manuscript_title': manifest.manuscript_title,
            'journal': manifest.journal,
            'revision_round': manifest.revision_round,
            'result_status': manifest.result_status.value,
        },
        'manuscript_source': {
            'file_name': manuscript_path.name,
            'sha256': sha256_file(manuscript_path),
            'modified': False,
        },
        'reviewer_comments': reviewer_payload,
        'manuscript_outline': list(structure.outline),
        'manuscript_structural_elements': [
            element.to_dict() for element in structure.elements
        ],
        'reference_section_boundary': structure.reference_section_boundary,
        'assessments': assessments,
    }


def _validate_locations(assessment: GapAnalysisAssessment) -> None:
    strings = [
        *assessment.target_sections,
        *assessment.target_objects,
        *(evidence.location or '' for evidence in assessment.manuscript_evidence),
    ]
    verified = set(assessment.verified_locations)
    for value in strings:
        if value and _ABSOLUTE_LOCATION.search(value) and value not in verified:
            raise ValueError(
                f'{assessment.comment_id} has an unverified absolute page/line location'
            )
    for evidence in assessment.manuscript_evidence:
        if (
            evidence.location
            and _ABSOLUTE_LOCATION.search(evidence.location)
            and not evidence.location_verified
            and evidence.location not in verified
        ):
            raise ValueError(
                f'{assessment.comment_id} has unverified manuscript evidence location'
            )


def import_gap_analysis(
    analysis_file: str | Path,
    source_comments: list[ReviewerComment],
) -> GapAnalysisImport:
    source = Path(analysis_file).expanduser().resolve()
    payload = read_json(source)
    if not isinstance(payload, dict) or not isinstance(payload.get('assessments'), list):
        raise ValueError('completed gap analysis must contain an assessments list')
    expected = {comment.comment_id: comment for comment in source_comments}
    raw_assessments = payload['assessments']
    ids = [item.get('comment_id') for item in raw_assessments if isinstance(item, dict)]
    unknown = sorted(set(ids) - set(expected))
    missing = sorted(set(expected) - set(ids))
    if unknown:
        raise ValueError('unknown comment IDs: ' + ', '.join(unknown))
    if missing:
        raise ValueError('missing assessments for comment IDs: ' + ', '.join(missing))
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate gap-analysis assessment comment IDs')

    assessments: list[GapAnalysisAssessment] = []
    for raw in raw_assessments:
        assessment = GapAnalysisAssessment.model_validate(raw)
        source_comment = expected[assessment.comment_id]
        if assessment.original_comment != source_comment.original_comment:
            raise ValueError(
                f'{assessment.comment_id} does not preserve exact reviewer comment text'
            )
        if assessment.coverage_status is None:
            raise ValueError(
                f'{assessment.comment_id} has no coverage_status'
            )
        if (
            assessment.coverage_status is CoverageStatus.FULLY_ADDRESSED
            and not assessment.manuscript_evidence
        ):
            raise ValueError(
                f'{assessment.comment_id} claims FULLY_ADDRESSED without manuscript evidence'
            )
        if (
            assessment.verification_status is EvidenceStatus.VERIFIED
            and not assessment.manuscript_evidence
        ):
            raise ValueError(
                f'{assessment.comment_id} claims VERIFIED without manuscript evidence'
            )
        if (
            assessment.experiment_completion_claimed
            and not assessment.experiment_evidence_ids
        ):
            raise ValueError(
                f'{assessment.comment_id} claims a completed experiment without evidence IDs'
            )
        _validate_locations(assessment)
        assessments.append(assessment)

    imported_at = datetime.now(UTC).isoformat()
    source_hash = sha256_file(source)
    imported = dict(payload)
    imported['import_metadata'] = {
        'imported_at': imported_at,
        'source_sha256': source_hash,
        'author_fields_preserved': True,
    }
    counts = Counter(item.coverage_status.value for item in assessments)
    return GapAnalysisImport(
        assessments=tuple(assessments),
        imported_payload=imported,
        source_hash=source_hash,
        imported_at=imported_at,
        coverage_counts=dict(sorted(counts.items())),
    )


def gap_analysis_report(imported: GapAnalysisImport, action_count: int) -> dict[str, Any]:
    return {
        'schema_version': 1,
        'imported_at': imported.imported_at,
        'source_sha256': imported.source_hash,
        'assessment_count': len(imported.assessments),
        'coverage_counts': imported.coverage_counts,
        'revision_action_count': action_count,
        'manuscript_modified': False,
        'semantic_assessments_generated_by_deterministic_code': False,
    }
