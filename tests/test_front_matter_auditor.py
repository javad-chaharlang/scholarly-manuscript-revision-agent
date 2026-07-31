from phase6_helpers import MANUSCRIPT
from scholarly_revision.tools.front_matter_auditor import audit_front_matter

def test_placeholder_and_running_header_detection() -> None:
    result=audit_front_matter(MANUSCRIPT,config={'running_header_patterns':['Old Journal Running Header']})
    text=' '.join(i.description for i in result.issues)
    assert 'placeholder' in text
    assert 'running header' in text
