from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from scholarly_revision.ui.components.studio import download, empty_state, load_json, page_header, state_banner
from scholarly_revision.ui.project_data import read_versions
from scholarly_revision.ui.state import redact_exception, save_uploaded_file

def render(orchestrator, project_root, actor) -> None:
    page_header('Manuscript Versions', 'Immutable source, backup, highlighted, and clean document lineage.',
                icon=':material/history:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    with st.container(horizontal=True):
        if st.button('Prepare draft package', icon=':material/package_2:', disabled=not allowed['prepare_revision_drafts']):
            try: orchestrator.prepare_revision_drafts(root, actor=actor); st.success('Blank draft package prepared.'); st.rerun()
            except Exception as exc: st.error(redact_exception(exc))
        download(root / 'working' / 'revision_draft_template.json', 'Download draft package', 'draft_package')
    upload = st.file_uploader('Completed revision drafts JSON', type=['json'], key='draft_import')
    if st.button('Import revision drafts', icon=':material/upload:',
                 disabled=not (allowed['import_revision_drafts'] and upload)):
        try:
            with TemporaryDirectory(dir=root.parent) as temp:
                orchestrator.import_revision_drafts(root, save_uploaded_file(upload, temp), actor=actor)
            st.success('Drafts imported for text approval.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    confirmed = st.checkbox('Create new immutable copies; never overwrite the source.', key='apply_confirm')
    if st.button('Apply and verify approved revisions', type='primary', icon=':material/publish:',
                 disabled=not (allowed['apply_revisions'] and confirmed)):
        try:
            with st.status('Applying approved exact text and verifying outputs...', expanded=True):
                orchestrator.apply_revisions(root, actor=actor)
            st.success('Versioned clean and highlighted manuscripts created and verified.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    versions = read_versions(root)
    if versions:
        st.dataframe(versions, hide_index=True)
    else: empty_state('No immutable versions yet', 'Versions appear after approved text is applied.')
    st.subheader('Output artifacts', anchor=False)
    for row in orchestrator.file_inventory(root):
        if row['role'] != 'outputs': continue
        with st.container(border=True, horizontal=True):
            st.write(f"**{row['file_name']}** · {row.get('version') or 'unversioned'} · {row['sha256'][:12]}…")
            download(root / 'outputs' / row['file_name'], 'Download', f"version_{row['file_name']}")
