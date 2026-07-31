from phase6_helpers import make_qa_project
from scholarly_revision.tools.highlight_auditor import audit_highlights

def test_policy_violation_and_clean_equivalence(tmp_path) -> None:
    root,highlighted,clean=make_qa_project(tmp_path)
    result=audit_highlights(highlighted,clean,change_log=root/'audit'/'change_log.json')
    assert result.text_equivalent
    assert result.clean_system_run_count==0
    assert any('incorrect repository highlight' in i.description for i in result.issues)
