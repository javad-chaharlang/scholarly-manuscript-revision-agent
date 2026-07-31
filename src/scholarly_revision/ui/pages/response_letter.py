from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import download_path, page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file


def render(orchestrator, project_root, actor) -> None:
    page_title('Response Letter', 'Prepare, generate, and verify one response per exact comment.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    if st.button(
        'Prepare response drafting package',
        disabled=not allowed['prepare_response'],
        key='prepare_response',
    ):
        try:
            orchestrator.prepare_response(root, actor=actor)
            st.success('Blank response package prepared; no scientific prose was generated.')
        except Exception as exc:
            st.error(redact_exception(exc))
    download_path(
        root / 'working' / 'response_drafting_package.json',
        label='Download response drafting package', key='download_response_package',
    )
    upload = st.file_uploader('Completed response draft (JSON)', type=['json'])
    if st.button(
        'Generate response letter',
        disabled=not (allowed['generate_response'] and upload is not None),
        key='generate_response',
    ):
        try:
            with TemporaryDirectory(dir=root.parent) as staging:
                source = save_uploaded_file(upload, staging)
                orchestrator.generate_response(root, source, actor=actor)
            st.success('Response letter generated as a local editable DOCX.')
        except Exception as exc:
            st.error(redact_exception(exc))
    if st.button(
        'Verify response letter',
        disabled=not allowed['verify_response'],
        key='verify_response',
    ):
        try:
            orchestrator.verify_response(root, actor=actor)
            st.success('Response verification completed.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
    package_path = root / 'working' / 'response_package.json'
    if package_path.is_file():
        package = read_json(package_path)
        entries = [
            item for section in package.get('sections', [])
            for item in section.get('entries', [])
        ]
        st.dataframe(entries, use_container_width=True, hide_index=True)
    report_path = root / 'audit' / 'response_verification_report.json'
    if report_path.is_file() and read_json(report_path).get('passed') is True:
        download_path(
            root / 'outputs' / 'Response_to_Reviewers.docx',
            label='Download verified response letter',
            key='download_verified_response',
        )
