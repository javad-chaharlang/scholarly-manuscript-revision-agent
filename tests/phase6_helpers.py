from __future__ import annotations
import json,shutil
from pathlib import Path
from scholarly_revision.tools.docx_clean_copy import create_clean_copy
from scholarly_revision.tools.docx_reader import read_docx
from scholarly_revision.tools.reviewer_parser import parse_reviewer_comments
from scholarly_revision.tools.workbook_builder import build_revision_workbook

TESTS=Path(__file__).parent
MANUSCRIPT=TESTS/'fixtures'/'synthetic_scientific_audit_manuscript.docx'
RESULTS=TESTS/'fixtures'/'synthetic_results_registry.json'
REFERENCES=TESTS/'fixtures'/'synthetic_reference_registry.json'
CONFIG=TESTS.parent/'templates'/'scientific_qa_config.yaml'
REVIEWERS=TESTS/'fixtures'/'synthetic_reviewer_comments.docx'

def make_qa_project(tmp_path:Path)->tuple[Path,Path,Path]:
    root=tmp_path/'private-project'
    for name in ('working','outputs','audit','config','rendered','input'):
        (root/name).mkdir(parents=True,exist_ok=True)
    highlighted=root/'outputs'/'Revised_Manuscript_Highlighted.docx'
    clean=root/'outputs'/'Revised_Manuscript_Clean.docx'
    shutil.copy2(MANUSCRIPT,highlighted);create_clean_copy(highlighted,clean)
    comments=parse_reviewer_comments(read_docx(REVIEWERS)).comments
    build_revision_workbook(root/'outputs'/'Revision_Master.xlsx',comments)
    change={'schema_version':1,'changes':[{'change_id':'CHG-0001','draft_id':'DRAFT-0001',
        'action_id':'ACT-0001','comment_ids':['R1-C01'],'operation':'REFERENCE_ADDITION',
        'target_section':'References','target_element_id':'REF-002','highlight':'YELLOW'}]}
    (root/'audit'/'change_log.json').write_text(json.dumps(change),encoding='utf-8')
    return root,highlighted,clean
