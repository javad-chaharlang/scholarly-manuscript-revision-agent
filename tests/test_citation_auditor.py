from phase6_helpers import MANUSCRIPT
import pytest
from scholarly_revision.tools.citation_auditor import audit_citations,parse_citation_group

def test_citation_range_parsing() -> None:
    assert parse_citation_group('[4–7]')==[4,5,6,7]
    assert parse_citation_group('[2, 3]')==[2,3]
    with pytest.raises(ValueError,match='descending'):parse_citation_group('[7-4]')

def test_missing_duplicate_and_malformed_detection() -> None:
    result=audit_citations(MANUSCRIPT,bibliography_count=4)
    descriptions=' '.join(i.description for i in result.issues)
    assert 'Duplicate citation' in descriptions
    assert 'Descending' in descriptions
    assert any('never cited' in i.description for i in result.issues)
