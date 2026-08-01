from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.ui.components.studio import empty_state, kpis, load_json, page_header, state_banner

def render(orchestrator, project_root, actor) -> None:
    page_header('Reference Audit', 'Structural citation and bibliography checks with explicit verification boundaries.',
                icon=':material/library_books:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    report = load_json(root / 'audit' / 'scientific_qa_report.json', {})
    if not report: empty_state('Reference audit not run', 'Run Scientific QA to populate structural findings.'); return
    issues = [i for i in report.get('issues', []) if i.get('category') in {'REFERENCE', 'CITATION'}]
    ref = report.get('auditor_summaries', {}).get('REFERENCE', {})
    cit = report.get('auditor_summaries', {}).get('CITATION', {})
    kpis([('Total references', ref.get('total_reference_count', 0), None),
          ('Cited references', len(cit.get('cited_reference_numbers', [])), None),
          ('Uncited references', sum(i.get('issue_id', '').startswith('REF-UNCITED') for i in issues), None),
          ('Missing numbers', sum('MISSING' in i.get('issue_id', '') for i in issues), None),
          ('Duplicates', sum('DUPLICATE' in i.get('issue_id', '') for i in issues), None),
          ('Unverified records', sum('UNVERIFIED' in i.get('issue_id', '') for i in issues), None),
          ('Reviewer-requested additions', 0, 'Loaded when a verified reference registry records reviewer mappings.')])
    st.info('DOI strings are checked structurally only. No external DOI or bibliographic validation is claimed.',
            icon=':material/info:')
    query = st.text_input('Search citation and bibliography issues', icon=':material/search:')
    filtered = [i for i in issues if not query or query.casefold() in str(i).casefold()]
    st.dataframe(filtered, hide_index=True)
    with st.container(horizontal=True):
        st.badge('Structurally verified', color='green')
        st.badge('Bibliographically verified', color='blue')
        st.badge('Externally unverified', color='orange')
