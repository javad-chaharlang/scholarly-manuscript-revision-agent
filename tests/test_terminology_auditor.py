from phase6_helpers import MANUSCRIPT
from scholarly_revision.tools.terminology_auditor import audit_terminology

def test_configured_variant_reporting() -> None:
    result=audit_terminology(MANUSCRIPT,[{'canonical':'adaptive-mode','variants':['adaptive method']}])
    assert result.term_frequencies['adaptive-mode']['adaptive-mode']==1
    assert result.term_frequencies['adaptive-mode']['adaptive method']==1
    assert result.issues[0].manual_review_required
