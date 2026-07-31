from phase6_helpers import MANUSCRIPT
from scholarly_revision.tools.figure_table_auditor import audit_figures_tables

def test_reference_mismatch_and_duplicate_caption() -> None:
    result=audit_figures_tables(MANUSCRIPT)
    text=' '.join(i.description for i in result.issues)
    assert 'non-existent figure' in text
    assert 'Duplicate table caption' in text or 'Duplicate figure/table caption' in text
