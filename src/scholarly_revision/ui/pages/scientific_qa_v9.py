from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from scholarly_revision.ui.components.studio import download, empty_state, kpis, load_json, page_header, state_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file

def render(orchestrator, project_root, actor) -> None:
    page_header('Scientific QA', 'Issue-management dashboard for deterministic integrity and consistency checks.',
                icon=':material/fact_check:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    if st.button('Run deterministic scientific QA', type='primary', icon=':material/play_arrow:',
                 disabled=not allowed['run_scientific_qa']):
        try:
            with st.status('Running local deterministic auditors...', expanded=True):
                orchestrator.run_scientific_qa(root, actor=actor)
            st.success('Scientific QA completed without external requests.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    report = load_json(root / 'audit' / 'scientific_qa_report.json', {})
    if not report: empty_state('No QA report', 'Apply verified revisions, then run the audit.'); return
    severity = report.get('count_by_severity', {})
    kpis([(key.title(), severity.get(key, 0), None) for key in
          ('BLOCKER', 'CRITICAL', 'MAJOR', 'MINOR', 'INFORMATIONAL')] +
         [('Manual review', report.get('manual_review_count', 0), None),
          ('Readiness', report.get('final_release_readiness', 'NOT_READY'), None)])
    issues = report.get('issues', [])
    with st.popover('Filters', icon=':material/filter_list:'):
        severities = st.multiselect('Severity', sorted({i.get('severity') for i in issues}))
        categories = st.multiselect('Category', sorted({i.get('category') for i in issues}))
        statuses = st.multiselect('Status', sorted({i.get('status') for i in issues}))
        sections = st.multiselect('Section', sorted({i.get('section') for i in issues if i.get('section')}))
        unresolved = st.toggle('Unresolved only', value=True)
    filtered = [i for i in issues if (not severities or i.get('severity') in severities)
                and (not categories or i.get('category') in categories)
                and (not statuses or i.get('status') in statuses)
                and (not sections or i.get('section') in sections)
                and (not unresolved or i.get('status') in {'OPEN', 'ACKNOWLEDGED'})]
    if filtered:
        issue_id = st.selectbox('Issue', [i['issue_id'] for i in filtered])
        item = next(i for i in filtered if i['issue_id'] == issue_id)
        with st.container(border=True, key='srs_blocker' if item.get('severity') == 'BLOCKER' else None):
            st.subheader(f"{item['issue_id']} · {item.get('severity')}", anchor=False)
            for label, key in [('Description', 'description'), ('Evidence', 'evidence'), ('Location', 'document_element_id'),
                               ('Related comments', 'related_comment_ids'), ('Related actions', 'related_action_ids'),
                               ('Resolution', 'resolution'), ('Verification', 'verified_by')]:
                st.markdown(f'**{label}:**'); st.write(item.get(key) or 'Not recorded')
    else: empty_state('No matching issues', 'Adjust the filters to inspect other findings.')
    download(root / 'audit' / 'qa_decision_template.json', 'Download decision package', 'qa_decision_download')
    upload = st.file_uploader('Completed QA decisions JSON', type=['json'], key='qa_decision_upload')
    if st.button('Validate and import QA decisions', icon=':material/upload:',
                 disabled=not (allowed['import_qa_decisions'] and upload)):
        try:
            with TemporaryDirectory(dir=root.parent) as temp:
                orchestrator.import_qa_decisions(root, save_uploaded_file(upload, temp), actor=actor)
            st.success('Explicit QA decisions imported and reverified.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    st.caption('Supported decisions: RESOLVE · ACCEPT_RISK · DEFER · NOT_APPLICABLE · NEED_MORE_EVIDENCE · MANUAL_CORRECTION_REQUIRED')
