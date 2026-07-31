'''Phase 7 response generation, consistency, gating, and release workflow.'''

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scholarly_revision.models.response_package import ResponsePackage
from scholarly_revision.services.final_release_service import evaluate_final_release
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.manual_visual_qa_service import (
    evaluate_manual_visual_qa,
)
from scholarly_revision.services.response_letter_service import (
    build_response_drafting_package, import_response_draft,
)
from scholarly_revision.services.response_verification_service import (
    ResponseVerificationResult, verify_response_package,
)
from scholarly_revision.tools.cross_document_consistency_auditor import (
    ConsistencyAuditReport, audit_cross_document_consistency,
)
from scholarly_revision.tools.release_package_builder import (
    ReleasePackageResult, build_release_package,
)
from scholarly_revision.tools.response_docx_builder import build_response_docx
from scholarly_revision.tools.workbook_builder import update_finalization_workbook


@dataclass(frozen=True, slots=True)
class ResponseGenerationResult:
    response_letter_path: Path
    response_package_path: Path
    generation_report_path: Path
    package: ResponsePackage


@dataclass(frozen=True, slots=True)
class FinalConsistencyResult:
    consistency_report: ConsistencyAuditReport
    consistency_json_path: Path
    consistency_csv_path: Path
    checklist_path: Path
    final_release_report_path: Path
    readiness: str


def prepare_response_drafts(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    build_response_drafting_package(root)
    return root / 'working' / 'response_drafting_package.json'


def generate_response_letter(
    project_root: str | Path,
    response_draft: str | Path,
) -> ResponseGenerationResult:
    root = Path(project_root).expanduser().resolve()
    letter_path = root / 'outputs' / 'Response_to_Reviewers.docx'
    if letter_path.exists():
        raise FileExistsError(f'response letter already exists: {letter_path}')
    package = import_response_draft(root, response_draft)
    letter_path = build_response_docx(package, letter_path)
    package_path = root / 'working' / 'response_package.json'
    report = {
        'schema_version': 1,
        'generated_at': datetime.now(UTC).isoformat(),
        'response_entry_count': len(package.entries),
        'count_by_status': {
            status: sum(item.response_status.value == status for item in package.entries)
            for status in sorted({item.response_status.value for item in package.entries})
        },
        'scientific_prose_generated_by_deterministic_code': False,
        'response_letter': letter_path.name,
        'package_status': package.package_status.value,
    }
    report_path = write_json(
        root / 'audit' / 'response_generation_report.json', report
    )
    update_finalization_workbook(
        root / 'outputs' / 'Revision_Master.xlsx', package, [], 'NOT_READY'
    )
    return ResponseGenerationResult(
        response_letter_path=letter_path,
        response_package_path=package_path,
        generation_report_path=report_path,
        package=package,
    )


def verify_response_letter(
    project_root: str | Path,
    response_letter: str | Path,
) -> ResponseVerificationResult:
    root = Path(project_root).expanduser().resolve()
    result = verify_response_package(root, response_letter=response_letter)
    update_finalization_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        result.package, [], 'NOT_READY',
    )
    return result


def _write_consistency_csv(path: Path, report: ConsistencyAuditReport) -> Path:
    fields = (
        'finding_id', 'category', 'severity', 'description',
        'related_comment_ids', 'related_action_ids', 'related_change_ids',
        'related_response_entry_ids', 'documents', 'status', 'resolution',
    )
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for finding in report.findings:
            row = finding.model_dump(mode='json')
            for key in (
                'related_comment_ids', 'related_action_ids', 'related_change_ids',
                'related_response_entry_ids', 'documents',
            ):
                row[key] = ';'.join(row[key])
            writer.writerow({key: row.get(key) for key in fields})
    return path


def run_final_consistency_check(
    project_root: str | Path,
    *,
    final_approval: dict | None = None,
) -> FinalConsistencyResult:
    root = Path(project_root).expanduser().resolve()
    package = ResponsePackage.model_validate(
        read_json(root / 'working' / 'response_package.json')
    )
    consistency = audit_cross_document_consistency(root, package)
    json_path = write_json(
        root / 'audit' / 'final_consistency_report.json',
        consistency.to_dict(),
    )
    csv_path = _write_consistency_csv(
        root / 'audit' / 'final_consistency_report.csv', consistency
    )
    release = evaluate_final_release(
        root, list(consistency.findings), final_approval=final_approval
    )
    if not evaluate_manual_visual_qa(root).passed:
        update_finalization_workbook(
            root / 'outputs' / 'Revision_Master.xlsx',
            package,
            consistency.findings,
            release.readiness.value,
        )
    return FinalConsistencyResult(
        consistency_report=consistency,
        consistency_json_path=json_path,
        consistency_csv_path=csv_path,
        checklist_path=root / 'audit' / 'final_release_checklist.json',
        final_release_report_path=root / 'outputs' / 'Final_Release_Report.json',
        readiness=release.readiness.value,
    )


def build_submission_package(
    project_root: str | Path,
    release_name: str,
) -> ReleasePackageResult:
    return build_release_package(project_root, release_name)
