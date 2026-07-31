from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import page_title, project_status_banner


def render(orchestrator, project_root, actor) -> None:
    page_title('Reviewer Comments', 'Exact, stable comment records are read-only.')
    project_status_banner(orchestrator, project_root)
    rows = read_json(Path(project_root) / 'working' / 'reviewer_comments.json')
    st.dataframe(rows, use_container_width=True, hide_index=True)
    allowed = orchestrator.available_actions(project_root)
    if st.button(
        'Confirm intake review complete',
        disabled=not allowed['complete_intake_review'],
        key='complete_intake_review',
    ):
        orchestrator.complete_intake_review(project_root, actor=actor)
        st.success('Intake review recorded. No approval was inferred.')
        st.rerun()
