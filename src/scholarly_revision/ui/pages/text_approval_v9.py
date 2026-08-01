from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.models.enums import RevisionTextDecision
from scholarly_revision.ui.components.studio import empty_state, load_json, page_header, state_banner
from scholarly_revision.ui.state import redact_exception

def render(orchestrator, project_root, actor) -> None:
    page_header('Text Approval', 'Exact-text gate: context, approved action, and proposed manuscript text.',
                icon=':material/approval:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    entries = load_json(root / 'working' / 'revision_drafts.json', {'drafts': []}).get('drafts', [])
    if not entries: empty_state('No draft texts', 'Prepare and import exact revision drafts first.'); return
    draft_id = st.selectbox('Draft', [i['draft']['draft_id'] for i in entries], key='text_draft')
    entry = next(i for i in entries if i['draft']['draft_id'] == draft_id); draft = entry['draft']
    action = entry.get('approved_action', {})
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True, height='stretch'):
            st.subheader('1. Comment and action', anchor=False)
            st.write(entry.get('comments') or draft.get('comment_ids'))
            st.write(action.get('proposed_revision_summary') or draft.get('drafting_rationale'))
    with c2:
        with st.container(border=True, height='stretch'):
            st.subheader('2. Existing context', anchor=False)
            st.text_area('Preceding paragraph', value=entry.get('preceding_context', ''), disabled=True)
            st.text_area('Target paragraph', value=draft.get('original_text_snapshot', ''), disabled=True)
            st.text_area('Following paragraph', value=entry.get('following_context', ''), disabled=True)
    with c3:
        with st.container(border=True, height='stretch'):
            st.subheader('3. Proposed revision', anchor=False)
            st.text_area('Proposed exact text', value=draft.get('proposed_text', ''), disabled=True, height=250)
            st.caption(f"Operation: {draft.get('operation')} · Highlight: {draft.get('highlight')} · Draft: {draft_id}")
    if draft.get('manual_handling_required'):
        st.error('Manual treatment required: ' + '; '.join(draft.get('manual_handling_reasons', [])))
    else:
        st.warning('Equations, fields, EndNote citations, tracked changes, hyperlinks, and complex objects require manual treatment when detected.')
    allowed = orchestrator.available_actions(root)
    with st.form('text_decision_v9', border=True):
        decision = st.selectbox('Explicit text decision', [i.value for i in RevisionTextDecision])
        maker = st.text_input('Decision maker', value=actor)
        modified = st.text_area('Author-modified exact text')
        note = st.text_area('Author note / rejection justification')
        evidence = st.text_area('Evidence request'); rewrite = st.text_area('Rewrite instruction')
        submitted = st.form_submit_button('Record exact-text decision', type='primary',
                                          disabled=not allowed['import_text_decisions'])
    if submitted:
        try:
            orchestrator.record_text_decision(root, draft_id=draft_id, decision=decision,
                decision_maker=maker, actor=actor, author_modified_text=modified or None,
                author_note=note or None, evidence_request=evidence or None,
                rewrite_instruction=rewrite or None)
            st.success('Exact text preserved and the explicit decision audited.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
