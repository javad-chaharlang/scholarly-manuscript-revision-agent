from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_task import AgentTaskType
from scholarly_revision.ui.agent_controls import render_agent_task_launcher
from scholarly_revision.models.enums import ApprovalDecision
from scholarly_revision.ui.components.studio import empty_state, load_json, page_header, state_banner
from scholarly_revision.ui.state import redact_exception

def render(orchestrator, project_root, actor) -> None:
    page_header('Revision Plan', 'Explicit action-level decisions with evidence and traceability.',
                icon=':material/task_alt:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    plan = load_json(root / 'working' / 'revision_plan.json', {'actions': []})
    actions = plan.get('actions', [])
    if not actions: empty_state('No revision plan', 'Import a completed gap analysis first.'); return
    st.badge(str(plan.get('approval_gate_status', 'NOT_READY')).replace('_', ' ').title(), color='orange')
    action_id = st.selectbox('Select action', [i['action_id'] for i in actions], key='plan_action')
    action = next(i for i in actions if i['action_id'] == action_id)
    render_agent_task_launcher(
        root, actor, task_type=AgentTaskType.REVISION_PLAN_DRAFT,
        label='Generate draft plan with Codex',
        purpose='Draft pending revision actions for the selected reviewer scope.',
        key=f'agent_plan_{action_id}', comment_ids=action.get('comment_ids', []),
        action_ids=[action_id],
        element_ids=[action['target_object']] if action.get('target_object') else [],
        context_policy=ContextPolicy.EXTENDED_SECTION_CONTEXT,
    )
    with st.container(border=True):
        st.subheader(action_id, anchor=False)
        st.caption(f"Comments: {', '.join(action.get('comment_ids', []))} · {action.get('change_type')} · {action.get('target_section')}")
        st.write(action.get('proposed_revision_summary') or 'No revision summary')
        st.markdown('**Rationale**'); st.write(action.get('rationale'))
        cols = st.columns(3)
        cols[0].write({'Evidence': action.get('evidence_requirements', []),
                       'References': action.get('reference_requirements', [])})
        cols[1].write({'Experiments': action.get('experiment_requirements', []),
                       'Statistics': action.get('statistical_requirements', [])})
        cols[2].write({'Unresolved': action.get('unresolved_questions', []),
                       'Highlight': action.get('highlight'), 'Approval': action.get('approval_state')})
    allowed = orchestrator.available_actions(root)
    with st.form('plan_decision_v9', border=True):
        decision = st.selectbox('Explicit decision', [i.value for i in ApprovalDecision])
        maker = st.text_input('Decision maker', value=actor)
        note = st.text_area('Author note / rejection justification')
        modified = st.text_area('Modified action text')
        evidence = st.text_area('Evidence request')
        confirm = st.checkbox('I confirm this scoped decision applies only to the displayed action.')
        submitted = st.form_submit_button('Record decision', type='primary',
                                          disabled=not allowed['record_plan_decision'] or not confirm)
    if submitted:
        try:
            orchestrator.record_plan_decision(root, action_id=action_id, decision=decision,
                decision_maker=maker, actor=actor, author_note=note or None,
                modified_action_text=modified or None, evidence_request=evidence or None)
            st.success('Scoped decision saved and audited.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
