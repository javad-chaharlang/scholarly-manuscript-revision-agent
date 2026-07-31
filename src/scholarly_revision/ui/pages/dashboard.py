from __future__ import annotations

import streamlit as st

from scholarly_revision.ui.components import page_title, project_status_banner


def render(orchestrator, project_root, actor) -> None:
    page_title('Dashboard', 'Safe workflow metrics and the next required action.')
    project_status_banner(orchestrator, project_root)
    data = orchestrator.dashboard(project_root)
    labels = (
        ('Comments', 'total_comments'),
        ('Manual review', 'manual_review_count'),
        ('Revision actions', 'revision_actions'),
        ('Approved actions', 'approved_actions'),
        ('Drafts awaiting approval', 'draft_texts_awaiting_approval'),
        ('QA blockers', 'qa_blockers'),
        ('Verified responses', 'verified_responses'),
        ('Release readiness', 'release_readiness'),
    )
    columns = st.columns(4)
    for index, (label, key) in enumerate(labels):
        columns[index % 4].metric(label, data[key])
    st.subheader('Comments by reviewer')
    st.dataframe(
        [{'source': key, 'count': value}
         for key, value in data['comments_by_reviewer'].items()],
        use_container_width=True, hide_index=True,
    )
    st.subheader('Read-only audit timeline')
    timeline = orchestrator.audit_timeline(project_root)
    st.dataframe(timeline, use_container_width=True, hide_index=True)
