from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from scholarly_revision.ui.components import download_path, page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file


def render(orchestrator, project_root, actor) -> None:
    page_title('Gap Analysis', 'Prepare and import source-grounded structured assessments.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    if st.button(
        'Prepare gap-analysis package',
        disabled=not allowed['prepare_gap_analysis'],
        key='prepare_gap',
    ):
        try:
            orchestrator.prepare_gap_analysis(root, actor=actor)
            st.success('Blank analysis package prepared; no semantic result was inferred.')
        except Exception as exc:
            st.error(redact_exception(exc))
    download_path(
        root / 'working' / 'gap_analysis_template.json',
        label='Download gap-analysis template', key='download_gap',
    )
    upload = st.file_uploader('Completed gap-analysis JSON', type=['json'])
    if st.button(
        'Import analysis and create plan',
        disabled=not (allowed['import_gap_analysis'] and upload is not None),
        key='import_gap',
    ):
        try:
            with TemporaryDirectory(dir=root.parent) as staging:
                source = save_uploaded_file(upload, staging)
                orchestrator.import_gap_analysis(root, source, actor=actor)
            st.success('Analysis imported and unapproved revision plan created.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
