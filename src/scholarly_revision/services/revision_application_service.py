'''Orchestrate safe application of explicitly approved exact revision text.'''

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docx import Document

from scholarly_revision.models.enums import RevisionDraftStatus
from scholarly_revision.models.revision_draft import ChangeRecord, RevisionDraft
from scholarly_revision.services.change_log_service import (
    build_change_records,
    validate_change_log_completeness,
    write_change_logs,
)
from scholarly_revision.services.document_version_service import (
    allocate_document_versions,
    finalize_document_versions,
)
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.services.revision_drafting_service import (
    load_project_revision_sources,
)
from scholarly_revision.tools.docx_clean_copy import (
    create_clean_copy,
    validate_text_equivalence,
)
from scholarly_revision.tools.docx_highlight_manager import audit_revision_highlights
from scholarly_revision.tools.docx_revision_applier import apply_docx_revisions
from scholarly_revision.tools.workbook_builder import (
    update_revision_execution_workbook,
)


@dataclass(frozen=True, slots=True)
class RevisionApplicationResult:
    highlighted_path: Path
    clean_path: Path
    versioned_highlighted_path: Path
    versioned_clean_path: Path
    change_log_json_path: Path
    change_log_csv_path: Path
    version_manifest_path: Path
    application_report_path: Path
    output_version: str
    applied_change_count: int
    blocked_change_count: int
    source_hash: str
    highlighted_hash: str
    clean_hash: str


def _load_draft_entries(root: Path) -> tuple[dict[str, Any], list[RevisionDraft]]:
    path = root / 'working' / 'revision_drafts.json'
    payload = read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get('drafts'), list):
        raise ValueError('revision_drafts.json must contain a drafts list')
    drafts = [
        RevisionDraft.model_validate(entry['draft'])
        for entry in payload['drafts']
        if isinstance(entry, dict) and isinstance(entry.get('draft'), dict)
    ]
    if len(drafts) != len(payload['drafts']):
        raise ValueError('revision_drafts.json contains malformed entries')
    return payload, drafts


def _update_applied_drafts(
    payload: dict[str, Any],
    applied: dict[str, ChangeRecord],
    output_version: str,
    timestamp: datetime,
) -> dict[str, Any]:
    result = dict(payload)
    entries: list[dict[str, Any]] = []
    for entry in payload['drafts']:
        draft = RevisionDraft.model_validate(entry['draft'])
        change = applied.get(draft.draft_id)
        updated = draft
        if change is not None:
            updated = draft.model_copy(update={
                'draft_status': RevisionDraftStatus.APPLIED,
                'application_status': 'APPLIED_AND_VERIFIED',
                'output_version': output_version,
                'verified_location': change.target_element_id,
                'updated_at': timestamp,
            })
            RevisionDraft.model_validate(updated.model_dump(mode='python'))
        item = dict(entry)
        item['draft'] = updated.model_dump(mode='json')
        entries.append(item)
    result['drafts'] = entries
    result['last_application_at'] = timestamp.isoformat()
    result['last_output_version'] = output_version
    return result


def apply_approved_revision_texts(
    project_root: str | Path,
    source_manuscript: str | Path,
) -> RevisionApplicationResult:
    root = Path(project_root).expanduser().resolve()
    source = Path(source_manuscript).expanduser().resolve()
    source_before = sha256_file(source)
    payload, drafts = _load_draft_entries(root)
    comments, actions, _, expected_hash = load_project_revision_sources(root)
    if source_before != expected_hash:
        raise ValueError('source manuscript SHA-256 does not match the drafting package')

    approved = [
        draft for draft in drafts
        if draft.draft_status.value == 'APPROVED'
        and draft.approval_state.value == 'APPROVED'
        and not draft.manual_handling_required
    ]
    blocked = len(drafts) - len(approved)
    if not approved:
        raise ValueError('no explicitly exact-text-approved drafts are eligible for application')
    if len({draft.source_document_hash for draft in approved}) != 1:
        raise ValueError('approved drafts do not share one source document hash')

    allocation = allocate_document_versions(root, source)
    mutations = apply_docx_revisions(
        source,
        allocation.highlighted_path,
        approved,
        expected_source_hash=expected_hash,
    )
    _, removed_highlights = create_clean_copy(
        allocation.highlighted_path, allocation.clean_path
    )
    if not validate_text_equivalence(
        allocation.highlighted_path, allocation.clean_path
    ):
        raise ValueError('highlighted and clean outputs do not have equivalent text')
    if sha256_file(source) != source_before:
        raise ValueError('source manuscript changed during application')

    applied_at = datetime.now(UTC)
    records = build_change_records(
        mutations,
        application_timestamp=applied_at,
        output_document_version=allocation.output_version,
    )
    validate_change_log_completeness(
        records, [mutation.draft_id for mutation in mutations]
    )
    json_log, csv_log = write_change_logs(root, records)
    highlighted_audit = audit_revision_highlights(allocation.highlighted_path)
    clean_audit = audit_revision_highlights(allocation.clean_path)
    if not highlighted_audit['passed']:
        raise ValueError('highlighted manuscript failed highlight policy audit')
    if clean_audit['system_highlight_count'] != 0:
        raise ValueError('clean manuscript retains system revision highlighting')

    manifest = finalize_document_versions(
        root,
        allocation,
        applied_change_ids=[record.change_id for record in records],
        verification_result='VERIFIED',
    )
    highlighted = root / 'outputs' / 'Revised_Manuscript_Highlighted.docx'
    clean = root / 'outputs' / 'Revised_Manuscript_Clean.docx'
    shutil.copy2(allocation.highlighted_path, highlighted)
    shutil.copy2(allocation.clean_path, clean)

    record_by_draft = {record.draft_id: record for record in records}
    updated_payload = _update_applied_drafts(
        payload, record_by_draft, allocation.output_version, applied_at
    )
    write_json(root / 'working' / 'revision_drafts.json', updated_payload)
    update_revision_execution_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        actions,
        [
            RevisionDraft.model_validate(entry['draft'])
            for entry in updated_payload['drafts']
        ],
        records,
        output_version=allocation.output_version,
        document_verification_status='VERIFIED',
        blocked_change_count=blocked,
    )

    report = {
        'schema_version': 1,
        'application_timestamp': applied_at.isoformat(),
        'source_document': {
            'sha256_before': source_before,
            'sha256_after': sha256_file(source),
            'unchanged': sha256_file(source) == source_before,
        },
        'backup_file': allocation.backup_path.name,
        'source_version': allocation.source_version,
        'output_version': allocation.output_version,
        'applied_change_count': len(records),
        'blocked_change_count': blocked,
        'applied_draft_ids': [record.draft_id for record in records],
        'blocked_draft_ids': [
            draft.draft_id for draft in drafts if draft.draft_id not in record_by_draft
        ],
        'highlighted_output': {
            'file_name': highlighted.name,
            'versioned_file_name': allocation.highlighted_path.name,
            'sha256': sha256_file(allocation.highlighted_path),
            'highlight_audit': highlighted_audit,
        },
        'clean_output': {
            'file_name': clean.name,
            'versioned_file_name': allocation.clean_path.name,
            'sha256': sha256_file(allocation.clean_path),
            'removed_system_highlights': removed_highlights,
            'highlight_audit': clean_audit,
        },
        'text_equivalent': True,
        'approval_inferred': False,
        'response_letter_generated': False,
        'final_release_approved': False,
    }
    report_path = write_json(
        root / 'audit' / 'revision_application_report.json', report
    )
    return RevisionApplicationResult(
        highlighted_path=highlighted,
        clean_path=clean,
        versioned_highlighted_path=allocation.highlighted_path,
        versioned_clean_path=allocation.clean_path,
        change_log_json_path=json_log,
        change_log_csv_path=csv_log,
        version_manifest_path=root / 'audit' / 'document_version_manifest.json',
        application_report_path=report_path,
        output_version=allocation.output_version,
        applied_change_count=len(records),
        blocked_change_count=blocked,
        source_hash=source_before,
        highlighted_hash=sha256_file(allocation.highlighted_path),
        clean_hash=sha256_file(allocation.clean_path),
    )


def verify_revision_output_package(
    project_root: str | Path,
    source_manuscript: str | Path,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    source = Path(source_manuscript).expanduser().resolve()
    highlighted = root / 'outputs' / 'Revised_Manuscript_Highlighted.docx'
    clean = root / 'outputs' / 'Revised_Manuscript_Clean.docx'
    _, drafts = _load_draft_entries(root)
    expected_hash = drafts[0].source_document_hash if drafts else None
    checks: dict[str, bool] = {}

    checks['source_document_unchanged'] = (
        expected_hash is not None and sha256_file(source) == expected_hash
    )
    Document(highlighted)
    Document(clean)
    checks['outputs_open_with_python_docx'] = True
    checks['highlighted_clean_text_equivalent'] = validate_text_equivalence(
        highlighted, clean
    )
    highlighted_audit = audit_revision_highlights(highlighted)
    clean_audit = audit_revision_highlights(clean)
    checks['highlight_policy_valid'] = bool(highlighted_audit['passed'])
    checks['clean_has_no_system_highlights'] = (
        clean_audit['system_highlight_count'] == 0
    )

    change_payload = read_json(root / 'audit' / 'change_log.json')
    changes = [
        ChangeRecord.model_validate(item)
        for item in change_payload.get('changes', [])
    ]
    applied = [draft for draft in drafts if draft.draft_status.value == 'APPLIED']
    approved_ids = {
        draft.draft_id for draft in drafts
        if draft.approval_state.value == 'APPROVED'
    }
    logged_ids = {change.draft_id for change in changes}
    checks['every_applied_change_has_verified_log'] = (
        {draft.draft_id for draft in applied} == logged_ids
        and all(change.verification_status == 'VERIFIED' for change in changes)
    )
    checks['no_unapproved_draft_applied'] = logged_ids.issubset(approved_ids)

    manifest = read_json(root / 'audit' / 'document_version_manifest.json')
    output_records = [
        item for item in manifest.get('versions', [])
        if item.get('role') in {'highlighted', 'clean'}
        and item.get('version') == manifest.get('latest_output_version')
    ]
    version_dir = root / 'outputs' / 'versions'
    checks['output_hashes_exist_and_match'] = len(output_records) == 2 and all(
        item.get('output_hash')
        and (version_dir / item['file_name']).is_file()
        and sha256_file(version_dir / item['file_name']) == item['output_hash']
        for item in output_records
    )
    passed = all(checks.values())
    report = {
        'schema_version': 1,
        'verified_at': datetime.now(UTC).isoformat(),
        'passed': passed,
        'checks': checks,
        'highlighted_audit': highlighted_audit,
        'clean_audit': clean_audit,
        'applied_change_count': len(changes),
        'output_version': manifest.get('latest_output_version'),
        'final_release_approved': False,
    }
    write_json(root / 'audit' / 'revision_output_verification_report.json', report)
    if not passed:
        failed = [name for name, value in checks.items() if not value]
        raise ValueError('revision output verification failed: ' + ', '.join(failed))
    return report
