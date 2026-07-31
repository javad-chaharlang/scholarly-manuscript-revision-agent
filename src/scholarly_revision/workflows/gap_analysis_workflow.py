'''Phase 4 orchestration for structure intake, import, planning, and workbook sync.'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.services.gap_analysis_service import (
    build_gap_analysis_package,
    gap_analysis_report,
    import_gap_analysis,
    read_json,
    write_json,
)
from scholarly_revision.services.revision_plan_service import (
    build_revision_plan,
    plan_has_approval,
)
from scholarly_revision.tools.manuscript_structure_reader import (
    read_manuscript_structure,
)
from scholarly_revision.tools.workbook_builder import update_revision_workbook


@dataclass(frozen=True, slots=True)
class PreparationResult:
    manuscript_structure_path: Path
    gap_analysis_input_path: Path
    gap_analysis_template_path: Path
    comment_count: int
    structural_element_count: int


@dataclass(frozen=True, slots=True)
class ImportResult:
    revision_plan_path: Path
    gap_analysis_report_path: Path
    workbook_path: Path
    action_count: int
    coverage_counts: dict[str, int]
    approval_gate_status: str


def _validate_root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    required = [
        root / 'working' / 'reviewer_comments.json',
        root / 'config' / 'project_manifest.yaml',
        root / 'outputs' / 'Revision_Master.xlsx',
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('incomplete Phase 3 project: ' + ', '.join(missing))
    return root


def prepare_gap_analysis(
    project_root: str | Path,
    manuscript_file: str | Path,
) -> PreparationResult:
    root = _validate_root(project_root)
    structure = read_manuscript_structure(manuscript_file)
    package = build_gap_analysis_package(root, structure, manuscript_file)
    structure_path = write_json(
        root / 'working' / 'manuscript_structure.json', structure.to_dict()
    )
    input_path = write_json(root / 'working' / 'gap_analysis_input.json', package)
    template_path = write_json(
        root / 'working' / 'gap_analysis_template.json', package
    )
    return PreparationResult(
        manuscript_structure_path=structure_path,
        gap_analysis_input_path=input_path,
        gap_analysis_template_path=template_path,
        comment_count=len(package['reviewer_comments']),
        structural_element_count=len(package['manuscript_structural_elements']),
    )


def import_and_plan(
    project_root: str | Path,
    analysis_file: str | Path,
) -> ImportResult:
    root = _validate_root(project_root)
    comments_raw = read_json(root / 'working' / 'reviewer_comments.json')
    comments = [ReviewerComment.model_validate(item) for item in comments_raw]
    imported = import_gap_analysis(analysis_file, comments)
    plan_path = root / 'working' / 'revision_plan.json'
    if plan_path.exists():
        existing = read_json(plan_path)
        if isinstance(existing, dict) and plan_has_approval(existing):
            raise ValueError('refusing to overwrite an approved revision plan')
    plan = build_revision_plan(
        imported.assessments,
        [comment.comment_id for comment in comments],
        imported.source_hash,
    )
    actions = [
        RevisionAction.model_validate(item) for item in plan['actions']
    ]
    write_json(root / 'working' / 'gap_analysis_imported.json', imported.imported_payload)
    write_json(plan_path, plan)
    report_path = write_json(
        root / 'audit' / 'gap_analysis_report.json',
        gap_analysis_report(imported, len(actions)),
    )
    workbook_path = root / 'outputs' / 'Revision_Master.xlsx'
    update_revision_workbook(
        workbook_path,
        comments,
        list(imported.assessments),
        actions,
        plan['approval_gate_status'],
    )
    return ImportResult(
        revision_plan_path=plan_path,
        gap_analysis_report_path=report_path,
        workbook_path=workbook_path,
        action_count=len(actions),
        coverage_counts=imported.coverage_counts,
        approval_gate_status=str(plan['approval_gate_status']),
    )
