'''Deterministic, confidentiality-safe change logging in JSON and CSV.'''

from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable

from scholarly_revision.models.enums import HighlightColor, RevisionOperation
from scholarly_revision.models.revision_draft import ChangeRecord
from scholarly_revision.services.gap_analysis_service import write_json
from scholarly_revision.tools.docx_revision_applier import AppliedMutation


CHANGE_LOG_FIELDS = (
    'change_id', 'draft_id', 'action_id', 'comment_ids', 'operation',
    'target_section', 'target_element_id', 'old_text_hash', 'new_text_hash',
    'old_text_summary', 'new_text_summary', 'highlight',
    'application_timestamp', 'output_document_version',
    'verification_status', 'warnings',
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def safe_text_summary(value: str, *, include_text: bool = False) -> str:
    if include_text:
        return value
    words = len(value.split())
    return f'content omitted; characters={len(value)}; words={words}; sha256={_hash(value)}'


def build_change_records(
    mutations: Iterable[AppliedMutation],
    *,
    application_timestamp: datetime,
    output_document_version: str,
    verification_status: str = 'VERIFIED',
    include_text_summaries: bool = False,
) -> list[ChangeRecord]:
    records: list[ChangeRecord] = []
    for number, mutation in enumerate(mutations, start=1):
        records.append(ChangeRecord(
            change_id=f'CHG-{number:04d}',
            draft_id=mutation.draft_id,
            action_id=mutation.action_id,
            comment_ids=list(mutation.comment_ids),
            operation=RevisionOperation(mutation.operation),
            target_section=mutation.target_section,
            target_element_id=mutation.target_element_id,
            old_text_hash=_hash(mutation.old_text),
            new_text_hash=_hash(mutation.new_text),
            old_text_summary=safe_text_summary(
                mutation.old_text, include_text=include_text_summaries
            ),
            new_text_summary=safe_text_summary(
                mutation.new_text, include_text=include_text_summaries
            ),
            highlight=HighlightColor(mutation.highlight),
            application_timestamp=application_timestamp,
            output_document_version=output_document_version,
            verification_status=verification_status,
            warnings=list(mutation.warnings),
        ))
    return records


def write_change_logs(
    project_root: str | Path,
    records: Iterable[ChangeRecord],
) -> tuple[Path, Path]:
    root = Path(project_root).expanduser().resolve()
    validated = [ChangeRecord.model_validate(item) for item in records]
    json_path = root / 'audit' / 'change_log.json'
    csv_path = root / 'audit' / 'change_log.csv'
    write_json(json_path, {
        'schema_version': 1,
        'confidential_text_included': False,
        'changes': [record.model_dump(mode='json') for record in validated],
    })
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CHANGE_LOG_FIELDS, lineterminator='\n')
        writer.writeheader()
        for record in validated:
            row = record.model_dump(mode='json')
            row['comment_ids'] = ';'.join(row['comment_ids'])
            row['warnings'] = ';'.join(row['warnings'])
            writer.writerow(row)
    return json_path, csv_path


def validate_change_log_completeness(
    records: Iterable[ChangeRecord],
    applied_draft_ids: Iterable[str],
) -> None:
    validated = [ChangeRecord.model_validate(item) for item in records]
    expected = list(applied_draft_ids)
    logged = [record.draft_id for record in validated]
    if logged != expected:
        raise ValueError('change log draft order does not match applied revisions')
    if any(record.verification_status != 'VERIFIED' for record in validated):
        raise ValueError('every applied change must have a VERIFIED log entry')
