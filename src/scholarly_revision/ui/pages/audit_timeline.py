from __future__ import annotations
import streamlit as st
from scholarly_revision.ui.components.studio import empty_state, page_header

def render(orchestrator, project_root, actor) -> None:
    page_header('Audit Timeline', 'Read-only, confidentiality-safe workflow history.',
                icon=':material/timeline:')
    if not project_root:
        empty_state('No project selected', 'Select a project to view its persisted audit events.')
        return
    events = list(reversed(orchestrator.audit_timeline(project_root)))
    if not events:
        empty_state('No audit events', 'Events appear as governed workflow actions are recorded.')
        return
    filters = st.multiselect('Event type', sorted({item['event_type'] for item in events}))
    for event in events:
        if filters and event['event_type'] not in filters: continue
        with st.container(border=True):
            st.markdown(f"**{event['event_type'].replace('_', ' ').title()}**")
            st.caption(f"{event['timestamp']} · {event['actor']} · {event['from_state'] or 'START'} → {event['to_state']}")
            if event.get('details'): st.json(event['details'], expanded=False)
