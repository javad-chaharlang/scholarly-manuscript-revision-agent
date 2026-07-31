from phase6_helpers import MANUSCRIPT,REFERENCES
from scholarly_revision.tools.reference_auditor import audit_references

def test_bibliography_sequence_uncited_and_duplicate_doi() -> None:
    result=audit_references(MANUSCRIPT,reference_registry=REFERENCES)
    assert result.total_reference_count==4
    text=' '.join(i.description for i in result.issues)
    assert 'missing number' in text
    assert 'Duplicate bibliography number' in text
    assert 'Duplicate DOI-like' in text
    assert result.bibliographic_verification_performed is False
