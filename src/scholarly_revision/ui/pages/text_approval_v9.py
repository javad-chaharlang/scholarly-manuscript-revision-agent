from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_task import AgentTaskType
from scholarly_revision.models.comment_approval import CommentApprovalDecision
from scholarly_revision.models.enums import RevisionTextDecision
from scholarly_revision.services.comment_approval_service import (
    APPROVAL_PACKET,
    APPROVAL_TEMPLATE,
    APPROVAL_WORKING,
)
from scholarly_revision.ui.agent_controls import render_agent_task_launcher
from scholarly_revision.ui.components.studio import (
    empty_state,
    load_json,
    page_header,
    state_banner,
)
from scholarly_revision.ui.state import redact_exception


def render(orchestrator, project_root, actor) -> None:
    page_header(
        'Text Approval',
        'Researcher gate for exact text, response, and linked changes.',
        icon=':material/approval:',
    )
    state_banner(orchestrator, project_root)
    root = Path(project_root)
    entries = load_json(
        root / 'working' / 'revision_drafts.json', {'drafts': []}
    ).get('drafts', [])
    if not entries:
        empty_state('No draft texts', 'Prepare and import exact revision drafts first.')
        return

    draft_id = st.selectbox(
        'Draft', [item['draft']['draft_id'] for item in entries], key='text_draft'
    )
    entry = next(item for item in entries if item['draft']['draft_id'] == draft_id)
    draft = entry['draft']
    action = entry.get('approved_action', {})
    draft_instruction = st.text_area(
        'Task-level rewrite instruction',
        key=f'agent_draft_instruction_{draft_id}',
        placeholder='Optional bounded drafting instruction for this exact target.',
    )
    render_agent_task_launcher(
        root,
        actor,
        task_type=AgentTaskType.REVISION_TEXT_DRAFT,
        label='Draft selected text with Codex',
        purpose=(
            'Draft proposed text for the approved action and exact target. '
            + (draft_instruction.strip() or 'No additional author instruction.')
        ),
        key=f'agent_text_{draft_id}',
        comment_ids=draft.get('comment_ids', []),
        action_ids=[draft['action_id']],
        element_ids=draft.get('target_element_ids', []),
        context_policy=ContextPolicy.SECTION_CONTEXT,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True, height='stretch'):
            st.subheader('1. Comment and action', anchor=False)
            st.write(entry.get('comments') or draft.get('comment_ids'))
            st.write(
                action.get('proposed_revision_summary')
                or draft.get('drafting_rationale')
            )
    with c2:
        with st.container(border=True, height='stretch'):
            st.subheader('2. Existing context', anchor=False)
            st.text_area(
                'Preceding paragraph',
                value=entry.get('preceding_context', ''),
                disabled=True,
            )
            st.text_area(
                'Target paragraph',
                value=draft.get('original_text_snapshot', ''),
                disabled=True,
            )
            st.text_area(
                'Following paragraph',
                value=entry.get('following_context', ''),
                disabled=True,
            )
    with c3:
        with st.container(border=True, height='stretch'):
            st.subheader('3. Proposed revision', anchor=False)
            st.text_area(
                'Proposed exact text',
                value=draft.get('proposed_text', ''),
                disabled=True,
                height=250,
            )
            st.caption(
                f"Operation: {draft.get('operation')} · "
                f"Highlight: {draft.get('highlight')} · Draft: {draft_id}"
            )
    if draft.get('manual_handling_required'):
        st.error(
            'Manual treatment required: '
            + '; '.join(draft.get('manual_handling_reasons', []))
        )
    else:
        st.warning(
            'Equations, fields, EndNote citations, tracked changes, hyperlinks, '
            'and complex objects require manual treatment when detected.'
        )
    allowed = orchestrator.available_actions(root)
    with st.form('text_decision_v9', border=True):
        decision = st.selectbox(
            'Explicit text decision', [item.value for item in RevisionTextDecision]
        )
        maker = st.text_input('Decision maker', value=actor)
        modified = st.text_area('Author-modified exact text')
        note = st.text_area('Author note / rejection justification')
        evidence = st.text_area('Evidence request')
        rewrite = st.text_area('Rewrite instruction')
        submitted = st.form_submit_button(
            'Record exact-text decision',
            type='primary',
            disabled=not allowed['import_text_decisions'],
        )
    if submitted:
        try:
            orchestrator.record_text_decision(
                root,
                draft_id=draft_id,
                decision=decision,
                decision_maker=maker,
                actor=actor,
                author_modified_text=modified or None,
                author_note=note or None,
                evidence_request=evidence or None,
                rewrite_instruction=rewrite or None,
            )
            st.success('Exact text preserved and the explicit decision audited.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))

    _render_comment_package_approval(orchestrator, root, actor, entries)


def _render_comment_package_approval(
    orchestrator, root: Path, actor: str, entries: list[dict]
) -> None:
    st.divider()
    st.subheader('Researcher approval by reviewer comment', anchor=False)
    st.caption(
        'Each decision covers the exact reviewer comment, the proposed response, '
        'and selected manuscript changes as one auditable package.'
    )
    decided_count = sum(
        item.get('draft', {}).get('author_decision') is not None for item in entries
    )
    st.progress(
        decided_count / len(entries),
        text=f'Exact-text decisions: {decided_count}/{len(entries)}',
    )
    if decided_count != len(entries):
        st.info('Complete an explicit exact-text decision for every draft first.')
        return

    allowed = orchestrator.available_actions(root)
    template_path = root / 'working' / APPROVAL_TEMPLATE
    working_path = root / 'working' / APPROVAL_WORKING
    packet_path = root / 'working' / APPROVAL_PACKET
    if not working_path.is_file():
        if st.button(
            'Prepare comment approval packages',
            type='primary',
            disabled=not allowed['prepare_comment_approval'],
        ):
            try:
                orchestrator.prepare_comment_approval(root, actor=actor)
                st.success('One approval package was created for every comment.')
                st.rerun()
            except Exception as exc:
                st.error(redact_exception(exc))
        return

    payload = load_json(working_path, {'records': []})
    records = payload.get('records', [])
    completed = sum(bool(item.get('decision')) for item in records)
    st.progress(
        completed / len(records) if records else 0.0,
        text=f'Comment-package decisions: {completed}/{len(records)}',
    )
    if packet_path.is_file():
        st.success(
            'The complete approval packet is locked. Only its eligible exact drafts '
            'may now be applied to the manuscript.'
        )
        return
    if not records:
        st.error(f'Approval template is empty: {template_path.name}')
        return

    comment_id = st.selectbox(
        'Reviewer/editor comment',
        [item['comment_id'] for item in records],
        format_func=lambda value: f"{value} · " + (
            'decided'
            if next(
                item for item in records if item['comment_id'] == value
            ).get('decision')
            else 'pending'
        ),
        key='comment_package_id',
    )
    record = next(item for item in records if item['comment_id'] == comment_id)
    proposed_changes = record.get('proposed_changes', [])
    response_instruction = st.text_area(
        'Response-drafting instruction',
        key=f'preapplication_response_instruction_{comment_id}',
        placeholder='Optional constraints for this response only.',
    )
    render_agent_task_launcher(
        root,
        actor,
        task_type=AgentTaskType.PREAPPLICATION_RESPONSE_DRAFT,
        label='Draft this response with Codex',
        purpose=(
            'Draft a source-grounded author response for the exact selected comment. '
            + (response_instruction.strip() or 'No additional author instruction.')
        ),
        key=f'preapplication_response_{comment_id}',
        comment_ids=[comment_id],
        action_ids=[],
        element_ids=[],
        context_policy=ContextPolicy.RESPONSE_CONTEXT,
    )

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown('**Exact reviewer comment**')
            st.text_area(
                'Verbatim source text',
                value=record.get('exact_comment', ''),
                disabled=True,
                height=180,
                label_visibility='collapsed',
            )
    with right:
        with st.container(border=True):
            st.markdown('**Current proposed response**')
            st.write(
                record.get('proposed_response')
                or 'No response has been drafted yet.'
            )

    st.markdown('**All linked manuscript changes**')
    if proposed_changes:
        st.dataframe(
            [
                {
                    'Draft': item.get('draft_id'),
                    'Section': item.get('target_section'),
                    'Operation': item.get('operation'),
                    'Text approval': item.get('text_approval_state'),
                    'Manual': item.get('manual_handling_required'),
                    'Approved manuscript text': item.get(
                        'approved_manuscript_text'
                    ),
                }
                for item in proposed_changes
            ],
            hide_index=True,
            use_container_width=True,
        )
        for change in proposed_changes:
            with st.expander(
                f"{change.get('draft_id')} · {change.get('target_section')}"
            ):
                st.text_area(
                    'Original text',
                    value=change.get('original_text_snapshot') or '',
                    disabled=True,
                    key=f"old_{comment_id}_{change.get('draft_id')}",
                )
                st.text_area(
                    'Researcher-approved manuscript text',
                    value=change.get('approved_manuscript_text') or '',
                    disabled=True,
                    key=f"new_{comment_id}_{change.get('draft_id')}",
                )
    else:
        st.info(
            'This comment has no linked manuscript change; its response still '
            'requires a decision.'
        )

    eligible_defaults = [
        item['draft_id']
        for item in proposed_changes
        if item.get('text_approval_state') == 'APPROVED'
        and not item.get('manual_handling_required')
    ]
    related_ids = list(record.get('related_draft_ids', []))
    decision_options = [item.value for item in CommentApprovalDecision]
    with st.form(f'comment_package_decision_{comment_id}', border=True):
        proposed_response = st.text_area(
            'Proposed response (editable before approval)',
            value=record.get('proposed_response', ''),
            height=180,
        )
        decision = st.selectbox(
            'Explicit package decision',
            decision_options,
            index=(
                decision_options.index(record['decision'])
                if record.get('decision') in decision_options
                else 0
            ),
        )
        approved_drafts = st.multiselect(
            'Exact linked drafts authorized for application',
            related_ids,
            default=[
                item
                for item in record.get('approved_draft_ids', eligible_defaults)
                if item in related_ids
            ],
            help='A shared draft must be authorized under every linked comment.',
        )
        modified_response = st.text_area(
            'Researcher-modified final response',
            value=record.get('author_modified_response') or '',
        )
        maker = st.text_input(
            'Decision maker', value=record.get('decision_maker') or actor
        )
        note = st.text_area(
            'Author note / defer or rejection rationale',
            value=record.get('author_note') or '',
        )
        evidence = st.text_area(
            'Evidence request', value=record.get('evidence_request') or ''
        )
        rewrite = st.text_area(
            'Rewrite instruction', value=record.get('rewrite_instruction') or ''
        )
        confirmed = st.checkbox(
            'I reviewed the exact comment, response, and every linked change shown above.'
        )
        submitted_package = st.form_submit_button(
            'Record atomic comment-package decision',
            type='primary',
            disabled=not allowed['record_comment_approval'],
        )
    if submitted_package:
        if not confirmed:
            st.error('Explicit review confirmation is required.')
            return
        try:
            orchestrator.record_comment_approval(
                root,
                comment_id=comment_id,
                proposed_response=proposed_response,
                decision=decision,
                decision_maker=maker,
                actor=actor,
                approved_draft_ids=approved_drafts,
                author_modified_response=modified_response or None,
                author_note=note or None,
                evidence_request=evidence or None,
                rewrite_instruction=rewrite or None,
            )
            st.success('The complete decision package was saved to the audit trail.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
