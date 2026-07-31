'''Build immutable allowlisted local submission packages with SHA-256 hashes.'''

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scholarly_revision.models.release import (
    FinalReleaseReport, ReleaseArtifact, ReleaseManifest,
)
from scholarly_revision.models.scientific_audit import FinalReleaseReadiness
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.project_workspace import sha256_file


@dataclass(frozen=True, slots=True)
class ReleasePackageResult:
    package_path: Path
    manifest_path: Path
    manifest: ReleaseManifest


_BASE_ARTIFACTS = (
    ('highlighted_manuscript', 'Revised_Manuscript_Highlighted.docx', 'Revised_Manuscript_Highlighted.docx'),
    ('clean_manuscript', 'Revised_Manuscript_Clean.docx', 'Revised_Manuscript_Clean.docx'),
    ('response_letter', 'Response_to_Reviewers.docx', 'Response_to_Reviewers.docx'),
    ('revision_workbook', 'Revision_Master.xlsx', 'Revision_Master.xlsx'),
    ('final_release_report', 'Final_Release_Report.json', 'Final_Release_Report.json'),
)


def _qa_artifact(outputs: Path) -> tuple[str, Path, str] | None:
    for source_name, release_name in (
        ('Final_QA_Report.docx', 'Final_QA_Report.docx'),
        ('Final_QA_Report.xlsx', 'Final_QA_Report.xlsx'),
        ('Scientific_QA_Report.xlsx', 'Final_QA_Report.xlsx'),
    ):
        source = outputs / source_name
        if source.is_file():
            return 'final_qa_report', source, release_name
    return None


def build_release_package(
    project_root: str | Path,
    release_name: str,
) -> ReleasePackageResult:
    root = Path(project_root).expanduser().resolve()
    report_path = root / 'outputs' / 'Final_Release_Report.json'
    report = FinalReleaseReport.model_validate(read_json(report_path))
    allowed = report.readiness is FinalReleaseReadiness.READY or (
        report.readiness is FinalReleaseReadiness.READY_WITH_WARNINGS
        and report.final_author_approved
    )
    if not allowed or not report.release_permitted:
        raise ValueError(
            'release package requires READY or explicitly author-approved READY_WITH_WARNINGS'
        )
    ReleaseManifest(
        release_name=release_name, created_at=datetime.now(UTC),
        readiness=report.readiness,
        final_author_approved=report.final_author_approved,
    )
    destination = root / 'Submission_Package' / release_name
    if destination.exists():
        raise FileExistsError(f'release package already exists: {destination}')
    outputs = root / 'outputs'
    candidates = [
        (role, outputs / source_name, release_file)
        for role, source_name, release_file in _BASE_ARTIFACTS
    ]
    qa = _qa_artifact(outputs)
    if qa is None:
        raise FileNotFoundError('approved final QA report is missing')
    candidates.append(qa)
    missing = [path.name for _, path, _ in candidates if not path.is_file()]
    if missing:
        raise FileNotFoundError('release artifacts are missing: ' + ', '.join(missing))

    destination.mkdir(parents=True)
    artifacts = []
    try:
        for role, source, release_file in candidates:
            target = destination / release_file
            shutil.copy2(source, target)
            artifacts.append(ReleaseArtifact(
                role=role,
                source_path=source.relative_to(root).as_posix(),
                release_path=target.relative_to(destination).as_posix(),
                sha256=sha256_file(target),
                size_bytes=target.stat().st_size,
            ))
        manifest = ReleaseManifest(
            release_name=release_name,
            created_at=datetime.now(UTC),
            readiness=report.readiness,
            final_author_approved=report.final_author_approved,
            artifacts=artifacts,
            excluded_categories=[
                'original reviewer files', 'original manuscript',
                'confidential experimental files', 'API keys', 'local databases',
                'internal prompts', 'temporary files', 'synthetic fixtures',
            ],
        )
        manifest_path = write_json(
            destination / 'Release_Manifest.json',
            manifest.model_dump(mode='json'),
        )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return ReleasePackageResult(
        package_path=destination,
        manifest_path=manifest_path,
        manifest=manifest,
    )
