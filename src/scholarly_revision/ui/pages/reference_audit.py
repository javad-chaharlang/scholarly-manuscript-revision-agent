from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import page_title, project_status_banner


def render(orchestrator, project_root, actor) -> None:
    page_title('Reference Audit', 'Read-only deterministic citation and reference findings.')
    project_status_banner(orchestrator, project_root)
    path = Path(project_root) / 'audit' / 'scientific_qa_report.json'
    if not path.is_file():
        st.info('Run Scientific QA to populate the reference audit.')
        return
    issues = [
        item for item in read_json(path).get('issues', [])
        if item.get('category') in {'REFERENCE', 'CITATION'}
    ]
    st.dataframe(issues, use_container_width=True, hide_index=True)
    st.caption('Structural checks do not claim external bibliographic verification.')
