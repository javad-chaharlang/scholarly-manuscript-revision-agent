'''Prepare, import, and validate explicit manual visual-QA decisions.'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholarly_revision.models.release import (
    MANUAL_VISUAL_QA_ARTIFACTS, ManualVisualQARecord,
)
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.project_workspace import sha256_file


@dataclass(frozen=True, slots=True)
class ManualVisualQAEvaluation:
    passed: bool
    reason: str
    record: ManualVisualQARecord | None
    record_path: Path


def _artifact_paths(root: Path) -> dict[str, Path]:
    return {
        name: root / 'outputs' / name
        for name in MANUAL_VISUAL_QA_ARTIFACTS
    }


def prepare_manual_visual_qa_template(project_root: str | Path) -> Path:
    '''Create an unapproved template; no inspection result is inferred.'''

    root = Path(project_root).expanduser().resolve()
    paths = _artifact_paths(root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            'manual visual-QA artifacts are missing: ' + ', '.join(missing)
        )
    destination = root / 'working' / 'manual_visual_qa_decision_template.json'
    if destination.exists():
        raise FileExistsError(
            f'manual visual-QA decision template already exists: {destination}'
        )
    payload = {
        'schema_version': 1,
        'decisions': [{
            'artifact_name': name,
            'artifact_sha256': sha256_file(paths[name]),
            'opened_successfully': None,
            'repair_warning_present': None,
            'layout_acceptable': None,
            'highlights_verified': None,
            'tables_and_captions_acceptable': None,
            'clean_highlight_text_equivalence_confirmed': None,
            'reviewer_notes': '',
            'decision_maker': '',
            'decision_timestamp': None,
            'decision': '',
        } for name in MANUAL_VISUAL_QA_ARTIFACTS],
    }
    return write_json(destination, payload)


def import_manual_visual_qa_decisions(
    project_root: str | Path,
    decision_file: str | Path | dict[str, Any],
) -> ManualVisualQARecord:
    '''Import explicit decisions after validating scope and artifact identity.'''

    root = Path(project_root).expanduser().resolve()
    payload = (
        read_json(decision_file)
        if isinstance(decision_file, (str, Path)) else decision_file
    )
    record = ManualVisualQARecord.model_validate(payload)
    paths = _artifact_paths(root)
    for decision in record.decisions:
        artifact = paths[decision.artifact_name]
        if not artifact.is_file():
            raise FileNotFoundError(
                f'manual visual-QA artifact is missing: {artifact}'
            )
        if sha256_file(artifact) != decision.artifact_sha256:
            raise ValueError(
                f'manual visual-QA decision is stale for {decision.artifact_name}'
            )
    write_json(
        root / 'audit' / 'manual_visual_qa_decisions.json',
        record.model_dump(mode='json'),
    )
    return record


def evaluate_manual_visual_qa(
    project_root: str | Path,
) -> ManualVisualQAEvaluation:
    '''Evaluate only an imported decision record against current artifacts.'''

    root = Path(project_root).expanduser().resolve()
    record_path = root / 'audit' / 'manual_visual_qa_decisions.json'
    if not record_path.is_file():
        return ManualVisualQAEvaluation(
            passed=False,
            reason='No explicit manual visual-QA decision record was imported.',
            record=None,
            record_path=record_path,
        )
    try:
        record = ManualVisualQARecord.model_validate(read_json(record_path))
        paths = _artifact_paths(root)
        for decision in record.decisions:
            artifact = paths[decision.artifact_name]
            if not artifact.is_file():
                raise FileNotFoundError(
                    f'manual visual-QA artifact is missing: {artifact}'
                )
            if sha256_file(artifact) != decision.artifact_sha256:
                raise ValueError(
                    f'manual visual-QA decision is stale for '
                    f'{decision.artifact_name}'
                )
    except Exception as exc:
        return ManualVisualQAEvaluation(
            passed=False,
            reason=f'{type(exc).__name__}: {exc}',
            record=None,
            record_path=record_path,
        )
    if not record.all_approved:
        return ManualVisualQAEvaluation(
            passed=False,
            reason='One or more explicit manual visual-QA decisions are REJECTED.',
            record=record,
            record_path=record_path,
        )
    return ManualVisualQAEvaluation(
        passed=True,
        reason='All five current artifacts have explicit APPROVED decisions.',
        record=record,
        record_path=record_path,
    )
