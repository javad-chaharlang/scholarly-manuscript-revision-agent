from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import download_path, page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file


def render(orchestrator, project_root, actor) -> None:
    page_title('Scientific QA', 'Run local deterministic audits and resolve findings explicitly.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    if st.button(
        'Run deterministic scientific QA',
        disabled=not allowed['run_scientific_qa'],
        key='run_scientific_qa',
    ):
        try:
            orchestrator.run_scientific_qa(root, actor=actor)
            st.success('Scientific QA completed.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
    report_path = root / 'audit' / 'scientific_qa_report.json'
    if report_path.is_file():
        report = read_json(report_path)
        st.metric('Blockers', report.get('blocker_count', 0))
        st.metric('Readiness', report.get('final_release_readiness', 'NOT_READY'))
        st.dataframe(report.get('issues', []), use_container_width=True, hide_index=True)
    download_path(
        root / 'audit' / 'qa_decision_template.json',
        label='Download QA decision template', key='download_qa_decisions',
    )
    upload = st.file_uploader('Completed QA decisions (JSON)', type=['json'])
    if st.button(
        'Import QA decisions',
        disabled=not (allowed['import_qa_decisions'] and upload is not None),
        key='import_qa_decisions',
    ):
        try:
            with TemporaryDirectory(dir=root.parent) as staging:
                source = save_uploaded_file(upload, staging)
                orchestrator.import_qa_decisions(root, source, actor=actor)
            st.success('QA decisions imported and resolution status reverified.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
