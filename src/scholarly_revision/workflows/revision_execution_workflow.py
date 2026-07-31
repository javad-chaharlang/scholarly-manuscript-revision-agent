'''Phase 5 drafting, approval, application, and verification orchestration.'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scholarly_revision.models.revision_draft import RevisionDraft
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.revision_application_service import (
    RevisionApplicationResult,
    apply_approved_revision_texts,
    verify_revision_output_package,
)
from scholarly_revision.services.revision_drafting_service import (
    build_revision_drafting_package,
    import_revision_drafts as validate_revision_drafts,
    load_project_revision_sources,
)
from scholarly_revision.services.revision_text_approval_service import (
    import_revision_text_decisions,
    revision_text_decision_template,
)
from scholarly_revision.tools.workbook_builder import (
    update_revision_execution_workbook,
)


@dataclass(frozen=True, slots=True)
class DraftPreparationResult:
    drafting_input_path: Path
    draft_template_path: Path
    drafting_report_path: Path
    draft_count: int
    blocked_action_count: int


@dataclass(frozen=True, slots=True)
class DraftImportResult:
    revision_drafts_path: Path
    import_report_path: Path
    draft_count: int


@dataclass(frozen=True, slots=True)
class TextDecisionImportResult:
    revision_drafts_path: Path
    decision_audit_path: Path
    decision_count: int
    approval_counts: dict[str, int]


def _root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    required = (
        root / 'working' / 'revision_plan.json',
        root / 'working' / 'reviewer_comments.json',
        root / 'working' / 'manuscript_structure.json',
        root / 'outputs' / 'Revision_Master.xlsx',
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('incomplete Phase 4 project: ' + ', '.join(missing))
    return root


def prepare_revision_drafts(project_root: str | Path) -> DraftPreparationResult:
    root = _root(project_root)
    drafting_input, template, report = build_revision_drafting_package(root)
    input_path = write_json(
        root / 'working' / 'revision_drafting_input.json', drafting_input
    )
    template_path = write_json(
        root / 'working' / 'revision_draft_template.json', template
    )
    report_path = write_json(
        root / 'audit' / 'drafting_report.json', report
    )
    comments, actions, _, _ = load_project_revision_sources(root)
    drafts = [
        RevisionDraft.model_validate(entry['draft']) for entry in template['drafts']
    ]
    update_revision_execution_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        actions,
        drafts,
        [],
        output_version=None,
        document_verification_status='NOT_RUN',
        blocked_change_count=report['actions_blocked'],
    )
    return DraftPreparationResult(
        drafting_input_path=input_path,
        draft_template_path=template_path,
        drafting_report_path=report_path,
        draft_count=report['drafts_prepared'],
        blocked_action_count=report['actions_blocked'],
    )


def import_completed_revision_drafts(
    project_root: str | Path,
    draft_file: str | Path,
) -> DraftImportResult:
    root = _root(project_root)
    imported, report = validate_revision_drafts(root, draft_file)
    draft_path = write_json(
        root / 'working' / 'revision_drafts.json', imported
    )
    report_path = write_json(
        root / 'audit' / 'revision_draft_import_report.json', report
    )
    comments, actions, _, _ = load_project_revision_sources(root)
    drafts = [
        RevisionDraft.model_validate(entry['draft']) for entry in imported['drafts']
    ]
    update_revision_execution_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        actions,
        drafts,
        [],
        output_version=None,
        document_verification_status='NOT_RUN',
    )
    return DraftImportResult(
        revision_drafts_path=draft_path,
        import_report_path=report_path,
        draft_count=len(drafts),
    )


def export_revision_text_decisions(
    project_root: str | Path,
    output_path: str | Path,
) -> Path:
    root = _root(project_root)
    payload = read_json(root / 'working' / 'revision_drafts.json')
    return write_json(output_path, revision_text_decision_template(payload))


def import_completed_text_decisions(
    project_root: str | Path,
    decisions_file: str | Path,
) -> TextDecisionImportResult:
    root = _root(project_root)
    draft_path = root / 'working' / 'revision_drafts.json'
    drafts_payload = read_json(draft_path)
    decisions_payload = read_json(decisions_file)
    updated, audit = import_revision_text_decisions(
        drafts_payload, decisions_payload
    )
    write_json(draft_path, updated)
    audit_path = write_json(
        root / 'audit' / 'revision_text_decisions.json', audit
    )
    comments, actions, _, _ = load_project_revision_sources(root)
    drafts = [
        RevisionDraft.model_validate(entry['draft']) for entry in updated['drafts']
    ]
    update_revision_execution_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        actions,
        drafts,
        [],
        output_version=None,
        document_verification_status='NOT_RUN',
    )
    approvals = updated.get('text_approval_summary', {})
    return TextDecisionImportResult(
        revision_drafts_path=draft_path,
        decision_audit_path=audit_path,
        decision_count=audit['decision_count'],
        approval_counts=dict(approvals),
    )


def apply_approved_revisions(
    project_root: str | Path,
    source_manuscript: str | Path,
) -> RevisionApplicationResult:
    return apply_approved_revision_texts(_root(project_root), source_manuscript)


def verify_revision_outputs(
    project_root: str | Path,
    source_manuscript: str | Path,
) -> dict[str, object]:
    return verify_revision_output_package(_root(project_root), source_manuscript)
