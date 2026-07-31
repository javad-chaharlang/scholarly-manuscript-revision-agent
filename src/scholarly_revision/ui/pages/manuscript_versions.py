from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import download_path, page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file


def render(orchestrator, project_root, actor) -> None:
    page_title('Manuscript Versions', 'Draft, apply, and inspect immutable manuscript versions.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    if st.button(
        'Prepare exact-text draft package',
        disabled=not allowed['prepare_revision_drafts'],
        key='prepare_revision_drafts',
    ):
        try:
            orchestrator.prepare_revision_drafts(root, actor=actor)
            st.success('Blank exact-text draft package prepared.')
        except Exception as exc:
            st.error(redact_exception(exc))
    download_path(
        root / 'working' / 'revision_draft_template.json',
        label='Download revision draft template', key='download_revision_drafts',
    )
    uploaded = st.file_uploader('Completed revision drafts (JSON)', type=['json'])
    if st.button(
        'Import completed revision drafts',
        disabled=not (allowed['import_revision_drafts'] and uploaded is not None),
        key='import_revision_drafts',
    ):
        try:
            with TemporaryDirectory(dir=root.parent) as staging:
                source = save_uploaded_file(uploaded, staging)
                orchestrator.import_revision_drafts(root, source, actor=actor)
            st.success('Revision drafts imported for exact-text approval.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
    confirmed = st.checkbox(
        'I understand this creates new versioned copies and never overwrites the source.',
        key='confirm_revision_application',
    )
    if st.button(
        'Apply and verify approved revisions',
        disabled=not (allowed['apply_revisions'] and confirmed),
        key='apply_revisions',
    ):
        try:
            orchestrator.apply_revisions(root, actor=actor)
            st.success('Approved revisions applied to new verified copies.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
    st.subheader('File hashes and versions')
    st.dataframe(orchestrator.file_inventory(root), use_container_width=True, hide_index=True)
    verification = root / 'audit' / 'revision_output_verification_report.json'
    verified = verification.is_file() and read_json(verification).get('passed') is True
    if verified:
        download_path(
            root / 'outputs' / 'Revised_Manuscript_Highlighted.docx',
            label='Download verified highlighted manuscript',
            key='download_highlighted',
        )
        download_path(
            root / 'outputs' / 'Revised_Manuscript_Clean.docx',
            label='Download verified clean manuscript',
            key='download_clean',
        )
