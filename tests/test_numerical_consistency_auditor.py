from phase6_helpers import MANUSCRIPT,RESULTS
from scholarly_revision.tools.numerical_consistency_auditor import audit_numerical_consistency

def test_numerical_and_percentage_mismatches() -> None:
    result=audit_numerical_consistency(MANUSCRIPT,results_registry=RESULTS,
        config={'sections':['Abstract','Results'],'percentage_tolerance':0.1})
    text=' '.join(i.description for i in result.issues)
    assert 'different numerical values' in text
    assert 'percentage improvement' in text
    assert result.scientific_verification_performed is False
