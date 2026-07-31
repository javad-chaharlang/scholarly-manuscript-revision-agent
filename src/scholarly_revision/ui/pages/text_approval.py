from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.models.enums import RevisionTextDecision
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception


def render(orchestrator, project_root, actor) -> None:
    page_title('Text Approval', 'Approve exact draft text separately from the revision plan.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    path = root / 'working' / 'revision_drafts.json'
    if not path.is_file():
        st.info('No completed revision drafts are awaiting review.')
        return
    entries = read_json(path).get('drafts', [])
    drafts = [item['draft'] for item in entries]
    st.dataframe(drafts, use_container_width=True, hide_index=True)
    if not drafts:
        return
    allowed = orchestrator.available_actions(root)
    with st.form('text_decision_form'):
        draft_id = st.selectbox('Draft ID', [item['draft_id'] for item in drafts])
        decision = st.selectbox('Decision', [item.value for item in RevisionTextDecision])
        maker = st.text_input('Decision maker', value=actor)
        modified = st.text_area('Author-modified exact text')
        note = st.text_area('Author note / rejection justification')
        evidence = st.text_area('Evidence request')
        rewrite = st.text_area('Rewrite instruction')
        submitted = st.form_submit_button(
            'Record text decision', disabled=not allowed['import_text_decisions'],
        )
    if submitted:
        try:
            orchestrator.record_text_decision(
                root, draft_id=draft_id, decision=decision,
                decision_maker=maker, actor=actor,
                author_modified_text=modified or None,
                author_note=note or None,
                evidence_request=evidence or None,
                rewrite_instruction=rewrite or None,
            )
            st.success('Exact-text decision recorded without inference.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
