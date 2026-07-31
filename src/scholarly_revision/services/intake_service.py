'''End-to-end deterministic intake for one local revision project.'''

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.enums import ResultStatus
from scholarly_revision.models.project import InputFiles, OutputNames, ProjectManifest
from scholarly_revision.services.config_loader import save_project_manifest
from scholarly_revision.services.project_workspace import (
    InputFileRecord,
    ProjectWorkspace,
    copy_input_file,
    create_project_workspace,
)
from scholarly_revision.tools.docx_reader import read_docx
from scholarly_revision.tools.reviewer_parser import parse_reviewer_comments
from scholarly_revision.tools.workbook_builder import build_revision_workbook


@dataclass(frozen=True, slots=True)
class IntakeResult:
    workspace: ProjectWorkspace
    manifest_path: Path
    reviewer_comments_path: Path
    intake_report_path: Path
    workbook_path: Path
    extracted_comment_ids: tuple[str, ...]
    manual_review_count: int
    warnings: tuple[str, ...]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write('\n')


def _validate_inputs(reviewer_file: Path, manuscript_file: Path | None) -> None:
    if reviewer_file.suffix.lower() != '.docx':
        raise ValueError('reviewer file must be a DOCX file in Phase 3')
    if not reviewer_file.is_file():
        raise FileNotFoundError(f'reviewer file not found: {reviewer_file}')
    if manuscript_file is not None:
        if manuscript_file.suffix.lower() not in {'.docx', '.pdf'}:
            raise ValueError('optional manuscript file must be DOCX or PDF')
        if not manuscript_file.is_file():
            raise FileNotFoundError(f'manuscript file not found: {manuscript_file}')


def _source_label(comment: Any) -> str:
    if comment.reviewer_source.value == 'REVIEWER':
        return f'REVIEWER_{comment.reviewer_number}'
    return comment.reviewer_source.value


def create_revision_project(
    *,
    workspace_root: str | Path,
    project_name: str,
    manuscript_id: str,
    reviewer_file: str | Path,
    manuscript_file: str | Path | None = None,
    journal: str | None = None,
    reviewer_count: int | None = None,
    force: bool = False,
) -> IntakeResult:
    '''Validate inputs and create the complete Phase 3 project package.'''

    if not manuscript_id or not manuscript_id.strip():
        raise ValueError('manuscript ID must be non-empty')
    if reviewer_count is not None and reviewer_count < 1:
        raise ValueError('reviewer count must be a positive integer')

    reviewer_source = Path(reviewer_file).expanduser().resolve()
    manuscript_source = (
        Path(manuscript_file).expanduser().resolve()
        if manuscript_file is not None
        else None
    )
    _validate_inputs(reviewer_source, manuscript_source)

    # Read and validate before creating a project directory so invalid reviewer
    # documents do not leave a partially initialized workspace.
    parse_result = parse_reviewer_comments(read_docx(reviewer_source))
    comments = list(parse_result.comments)
    detected_reviewer_count = max(
        (comment.reviewer_number or 0 for comment in comments), default=0
    )
    effective_reviewer_count = reviewer_count or max(1, detected_reviewer_count)
    if effective_reviewer_count < detected_reviewer_count:
        raise ValueError(
            'reviewer count is smaller than a reviewer number found in the file'
        )

    workspace = create_project_workspace(
        workspace_root, project_name, force=force
    )
    inventory: list[InputFileRecord] = [
        copy_input_file(reviewer_source, workspace, 'reviewer_comments')
    ]
    if manuscript_source is not None:
        inventory.append(copy_input_file(manuscript_source, workspace, 'manuscript'))

    created_at = datetime.now(UTC)
    copied_reviewer = next(item for item in inventory if item.role == 'reviewer_comments')
    copied_manuscript = next(
        (item for item in inventory if item.role == 'manuscript'), None
    )
    manifest = ProjectManifest(
        project_name=project_name.strip(),
        manuscript_id=manuscript_id.strip(),
        journal=(journal or 'UNSPECIFIED').strip() or 'UNSPECIFIED',
        revision_round=1,
        manuscript_language='English',
        response_language='English',
        citation_style='journal-required',
        reviewer_count=effective_reviewer_count,
        result_status=ResultStatus.DRAFT,
        input_files=InputFiles(
            manuscript=copied_manuscript.name if copied_manuscript else None,
            reviewer_comments=[copied_reviewer.name],
        ),
        output_names=OutputNames(
            highlighted_manuscript='manuscript_revised_highlighted.docx',
            clean_manuscript='manuscript_revised_clean.docx',
            revision_workbook='Revision_Master.xlsx',
            response_letter='response_to_reviewers.docx',
            qa_report='final_qa_report.md',
            audit_log='revision_audit.jsonl',
        ),
        created_at=created_at,
        updated_at=created_at,
    )

    manifest_path = workspace.config / 'project_manifest.yaml'
    comments_path = workspace.working / 'reviewer_comments.json'
    report_path = workspace.audit / 'intake_report.json'
    workbook_path = workspace.outputs / 'Revision_Master.xlsx'
    save_project_manifest(manifest, manifest_path)
    _write_json(
        comments_path,
        [comment.model_dump(mode='json') for comment in comments],
    )

    missing_inputs: list[str] = []
    warnings = list(parse_result.warnings)
    if manuscript_source is None:
        missing_inputs.append('manuscript_file (optional)')
        warnings.append(
            'Optional manuscript file was not provided; manuscript parsing was skipped.'
        )
    counts = Counter(_source_label(comment) for comment in comments)
    manual_review_count = sum(
        comment.manual_review_required for comment in comments
    )
    inventory_payload = [item.to_dict() for item in inventory]
    report = {
        'project_slug': workspace.slug,
        'workspace_paths': {
            'project_root': '.',
            **{name: name for name in ('input', 'working', 'outputs', 'rendered', 'audit', 'config')},
        },
        'input_file_inventory': inventory_payload,
        'hash_values': {
            item.stored_path: item.sha256 for item in inventory
        },
        'extracted_comment_count': len(comments),
        'count_by_reviewer_or_source': dict(sorted(counts.items())),
        'manual_review_required_count': manual_review_count,
        'warnings': list(dict.fromkeys(warnings)),
        'missing_inputs': missing_inputs,
        'result_status': 'DRAFT',
        'created_at': created_at.isoformat(),
    }
    _write_json(report_path, report)
    build_revision_workbook(
        workbook_path,
        comments,
        project_info={
            'Project Name': manifest.project_name,
            'Project Slug': workspace.slug,
            'Manuscript ID': manifest.manuscript_id,
            'Journal': manifest.journal,
            'Revision Round': manifest.revision_round,
            'Reviewer Count': manifest.reviewer_count,
            'Result Status': manifest.result_status.value,
            'Created At': created_at.isoformat(),
        },
    )
    return IntakeResult(
        workspace=workspace,
        manifest_path=manifest_path,
        reviewer_comments_path=comments_path,
        intake_report_path=report_path,
        workbook_path=workbook_path,
        extracted_comment_ids=tuple(comment.comment_id for comment in comments),
        manual_review_count=manual_review_count,
        warnings=tuple(dict.fromkeys(warnings)),
    )
