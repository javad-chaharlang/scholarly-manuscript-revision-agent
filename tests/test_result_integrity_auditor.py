from phase6_helpers import MANUSCRIPT,RESULTS
from scholarly_revision.tools.result_integrity_auditor import audit_result_integrity

def test_draft_final_conflict_and_missing_evidence_blocker() -> None:
    result=audit_result_integrity(MANUSCRIPT,RESULTS)
    blockers=[i for i in result.issues if i.severity.value=='BLOCKER']
    assert blockers
    text=' '.join(i.description for i in blockers)
    assert 'VERIFIED source evidence' in text
    assert 'Claimed experiment' in text
