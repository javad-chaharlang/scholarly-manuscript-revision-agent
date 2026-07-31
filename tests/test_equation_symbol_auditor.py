from phase6_helpers import MANUSCRIPT
from scholarly_revision.tools.equation_symbol_auditor import audit_equations_symbols

def test_equation_duplication_undefined_and_conflicting_symbol() -> None:
    result=audit_equations_symbols(MANUSCRIPT)
    text=' '.join(i.description for i in result.issues)
    assert 'Duplicate equation number' in text
    assert 'first used before' in text
    assert 'Conflicting definitions' in text
    assert result.mathematical_correctness_checked is False
