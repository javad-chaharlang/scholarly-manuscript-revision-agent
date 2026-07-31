from datetime import UTC, datetime
from pathlib import Path

import pytest

from scholarly_revision.services.change_log_service import (
    build_change_records,
    validate_change_log_completeness,
    write_change_logs,
)
from scholarly_revision.tools.docx_revision_applier import AppliedMutation


def mutation() -> AppliedMutation:
    return AppliedMutation(
        draft_id='DRAFT-0001', action_id='ACT-0001',
        comment_ids=('R1-C01',), operation='REPLACE_PARAGRAPH',
        target_section='Introduction', target_element_id='PAR-0001',
        old_text='Confidential old synthetic text.',
        new_text='Confidential new synthetic text.', highlight='YELLOW',
    )


def test_complete_confidentiality_safe_json_and_csv(tmp_path: Path) -> None:
    records = build_change_records(
        [mutation()], application_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        output_document_version='v002',
    )
    json_path, csv_path = write_change_logs(tmp_path, records)
    text = json_path.read_text(encoding='utf-8')
    assert 'Confidential old synthetic text.' not in text
    assert 'characters=' in text
    assert csv_path.is_file()
    validate_change_log_completeness(records, ['DRAFT-0001'])
    with pytest.raises(ValueError, match='draft order'):
        validate_change_log_completeness(records, ['DRAFT-9999'])
