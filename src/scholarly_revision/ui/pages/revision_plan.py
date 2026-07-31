from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.models.enums import ApprovalDecision
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception


def render(orchestrator, project_root, actor) -> None:
    page_title('Revision Plan', 'Record one explicit author decision per proposed action.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    path = root / 'working' / 'revision_plan.json'
    if not path.is_file():
        st.info('No revision plan has been imported.')
        return
    plan = read_json(path)
    actions = plan.get('actions', [])
    st.dataframe(actions, use_container_width=True, hide_index=True)
    if not actions:
        return
    allowed = orchestrator.available_actions(root)
    with st.form('plan_decision_form'):
        action_id = st.selectbox('Action ID', [item['action_id'] for item in actions])
        decision = st.selectbox('Decision', [item.value for item in ApprovalDecision])
        maker = st.text_input('Decision maker', value=actor)
        author_note = st.text_area('Author note / rejection justification')
        modified = st.text_area('Modified action text')
        evidence_request = st.text_area('Evidence request')
        submitted = st.form_submit_button(
            'Record decision', disabled=not allowed['record_plan_decision'],
        )
    if submitted:
        try:
            orchestrator.record_plan_decision(
                root, action_id=action_id, decision=decision,
                decision_maker=maker, actor=actor,
                author_note=author_note or None,
                modified_action_text=modified or None,
                evidence_request=evidence_request or None,
            )
            st.success('Scoped plan decision recorded.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
