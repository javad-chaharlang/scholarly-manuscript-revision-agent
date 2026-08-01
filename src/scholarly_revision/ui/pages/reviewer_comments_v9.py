from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_task import AgentTaskType
from scholarly_revision.ui.agent_controls import render_agent_task_launcher
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components.studio import empty_state, page_header, state_banner
from scholarly_revision.ui.state import redact_exception

def render(orchestrator, project_root, actor) -> None:
    page_header('Reviewer Comments', 'Searchable master-detail inventory with immutable IDs and exact source text.',
                icon=':material/rate_review:')
    state_banner(orchestrator, project_root)
    path = Path(project_root) / 'working' / 'reviewer_comments.json'
    if not path.is_file():
        empty_state('No reviewer inventory', 'Complete intake to create exact comment records.'); return
    comments = read_json(path)
    query = st.text_input('Search comments', icon=':material/search:')
    with st.popover('Filters', icon=':material/filter_list:'):
        reviewers = st.multiselect('Reviewer', sorted({str(i.get('reviewer_number') or i.get('reviewer_source')) for i in comments}))
        categories = st.multiselect('Category', sorted({c for i in comments for c in i.get('categories', [])}))
        statuses = st.multiselect('Status', sorted({i.get('status') for i in comments}))
        priorities = st.multiselect('Priority', sorted({i.get('priority') for i in comments}))
        unresolved = st.toggle('Unresolved only')
        manual = st.toggle('Manual review only')
    filtered = []
    for item in comments:
        reviewer = str(item.get('reviewer_number') or item.get('reviewer_source'))
        haystack = f"{item.get('comment_id')} {item.get('original_comment')} {item.get('normalized_comment') or ''}".casefold()
        if query and query.casefold() not in haystack: continue
        if reviewers and reviewer not in reviewers: continue
        if categories and not set(categories).intersection(item.get('categories', [])): continue
        if statuses and item.get('status') not in statuses: continue
        if priorities and item.get('priority') not in priorities: continue
        if unresolved and item.get('status') in {'VERIFIED', 'NOT_APPLICABLE'}: continue
        if manual and not item.get('manual_review_required'): continue
        filtered.append(item)
    if not filtered:
        empty_state('No matching comments', 'Clear filters to restore the full inventory.'); return
    left, right = st.columns([1, 2])
    with left:
        options = {f"{i['comment_id']} · {i.get('priority')} · {i.get('status')}": i for i in filtered}
        selected_label = st.radio('Comment list', list(options), key='selected_comment')
        item = options[selected_label]
        source = item.get('reviewer_number')
        color = 'yellow' if source == 1 else 'green' if source == 2 else 'violet'
        st.badge(f"Reviewer {source}" if source else item.get('reviewer_source'), color=color)
        st.badge(item.get('priority', 'UNKNOWN'), color='red' if item.get('priority') == 'CRITICAL' else 'orange')
        if item.get('manual_review_required'): st.badge('Manual review', color='red')
    with right:
        with st.container(border=True):
            st.subheader(f"{item['comment_id']} · Exact original comment", anchor=False)
            st.text_area('Exact original comment', value=item.get('original_comment', ''),
                         height=180, disabled=True, key=f"exact_{item['comment_id']}")
            st.caption('Read-only: exact reviewer text and stable ID cannot be edited here.')
        fields = [('Normalized comment', item.get('normalized_comment')),
                  ('Interpretation', item.get('interpretation')),
                  ('Required actions', item.get('required_actions')),
                  ('Target sections', item.get('target_sections')),
                  ('Evidence status', item.get('evidence_status')),
                  ('Author notes', item.get('notes')),
                  ('Related comments', item.get('shared_with'))]
        for label, value in fields:
            with st.expander(label): st.write(value or 'Not recorded')
    selected_comment_id = item['comment_id']
    render_agent_task_launcher(
        project_root, actor, task_type=AgentTaskType.COMMENT_INTERPRETATION,
        label='Run Comment Interpretation with Codex',
        purpose='Interpret one exact reviewer comment without changing its identity.',
        key=f'agent_interpret_{selected_comment_id}',
        comment_ids=[selected_comment_id],
        context_policy=ContextPolicy.MINIMAL_COMMENT_CONTEXT,
    )
    allowed = orchestrator.available_actions(project_root)
    if st.button('Confirm intake review complete', icon=':material/check_circle:',
                 disabled=not allowed['complete_intake_review']):
        try:
            orchestrator.complete_intake_review(project_root, actor=actor)
            st.success('Intake review recorded; no split, merge, or approval was inferred.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    st.info('Split and merge operations require an explicit governed author-decision service and are never performed silently.',
            icon=':material/gavel:')
