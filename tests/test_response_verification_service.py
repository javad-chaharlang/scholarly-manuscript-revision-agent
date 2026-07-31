from pathlib import Path

from docx import Document

from phase7_helpers import make_ready_phase7_project
from scholarly_revision.models.response_package import (
    EvidenceStatus, LocationStatus, ResponseEntry, ResponsePackage, ResponseStatus,
)
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.response_verification_service import verify_response_package


def test_verified_ready_response_passes(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    result = verify_response_package(
        root, response_letter=root / 'outputs' / 'Response_to_Reviewers.docx'
    )
    assert result.passed
    assert result.verified_count == 1


def test_invalid_page_location_and_missing_evidence_block(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    package = ResponsePackage.model_validate(
        read_json(root / 'working' / 'response_package.json')
    )
    entry = ResponseEntry.model_validate({
        **package.entries[0].model_dump(mode='python'),
        'response_status': ResponseStatus.APPROVED,
        'verified_locations': ['Page 9, Lines 3-4'],
        'location_status': LocationStatus.PAGE_AND_LINES_VERIFIED,
        'related_evidence_ids': ['EVIDENCE-404'],
        'evidence_status': EvidenceStatus.VERIFIED,
    })
    section = package.sections[0].model_copy(update={'entries': [entry]})
    changed = ResponsePackage.model_validate({
        **package.model_dump(mode='python'),
        'sections': [section], 'package_status': ResponseStatus.DRAFTED,
    })
    result = verify_response_package(root, changed)
    codes = {item['code'] for item in result.issues}
    assert {'INVALID_LOCATION', 'MISSING_EVIDENCE'} <= codes
    assert not result.passed


def test_docx_response_field_mismatch_blocks_verification(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    path = root / 'outputs' / 'Response_to_Reviewers.docx'
    document = Document(path)
    response_table = next(table for table in document.tables if len(table.rows) == 5)
    response_table.rows[1].cells[0].text = (
        "Author's response:\nAltered response text."
    )
    document.save(path)
    result = verify_response_package(root, response_letter=path)
    assert 'DOCX_AUTHOR_RESPONSE_MISMATCH' in {
        item['code'] for item in result.issues
    }
    assert not result.passed
