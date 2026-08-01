from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from scholarly_revision.ui.components.studio import download, empty_state, load_json, page_header, state_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file

def render(orchestrator, project_root, actor) -> None:
    page_header('Response Letter', 'Point-by-point response workspace linked to verified manuscript changes.',
                icon=':material/draft:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    with st.container(horizontal=True):
        if st.button('Prepare response workspace', icon=':material/package_2:', disabled=not allowed['prepare_response']):
            try: orchestrator.prepare_response(root, actor=actor); st.success('Blank response fields prepared.'); st.rerun()
            except Exception as exc: st.error(redact_exception(exc))
        download(root / 'working' / 'response_drafting_package.json', 'Download drafting package', 'response_package')
    package = load_json(root / 'working' / 'response_package.json', {})
    entries = [i for section in package.get('sections', []) for i in section.get('entries', [])]
    if entries:
        reviewers = sorted({f"{i.get('reviewer_source')} {i.get('reviewer_number') or ''}" for i in entries})
        reviewer = st.segmented_control('Reviewer', reviewers, default=reviewers[0])
        visible = [i for i in entries if f"{i.get('reviewer_source')} {i.get('reviewer_number') or ''}" == reviewer]
        st.progress(sum(i.get('response_status') == 'VERIFIED' for i in visible) / len(visible),
                    text=f"{sum(i.get('response_status') == 'VERIFIED' for i in visible)} of {len(visible)} verified")
        selected = st.selectbox('Comment', [i['comment_id'] for i in visible])
        item = next(i for i in visible if i['comment_id'] == selected)
        c1, c2, c3, c4 = st.columns(4)
        c1.text_area('Reviewer comment', item.get('exact_comment', ''), disabled=True, height=220)
        c2.write(item.get('related_action_ids') or 'No related action')
        c3.write({'Changes': item.get('related_change_ids'), 'Location': item.get('verified_locations'),
                  'Highlight': item.get('highlight')})
        c4.text_area('Author response', item.get('author_response') or '', disabled=True, height=220)
        st.caption(f"Evidence: {item.get('related_evidence_ids')} · References: {item.get('related_reference_ids')} · Status: {item.get('response_status')}")
    else: empty_state('No response entries', 'Prepare and complete the structured response drafting package.')
    upload = st.file_uploader('Completed response draft JSON', type=['json'], key='response_upload')
    if st.button('Generate Word response letter', icon=':material/description:',
                 disabled=not (allowed['generate_response'] and upload)):
        try:
            with TemporaryDirectory(dir=root.parent) as temp:
                orchestrator.generate_response(root, save_uploaded_file(upload, temp), actor=actor)
            st.success('Editable Word response created.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    if st.button('Verify response letter', type='primary', icon=':material/verified:',
                 disabled=not allowed['verify_response']):
        try: orchestrator.verify_response(root, actor=actor); st.success('Response verification completed.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    report = load_json(root / 'audit' / 'response_verification_report.json', {})
    if report:
        st.metric('Verified responses', report.get('verified_count', 0), border=True)
        st.metric('Missing / blocked responses', report.get('blocked_count', 0), border=True)
        st.dataframe(report.get('issues', []), hide_index=True)
        download(root / 'outputs' / 'Response_to_Reviewers.docx', 'Download response letter', 'response_letter',
                 disabled=report.get('passed') is not True)
