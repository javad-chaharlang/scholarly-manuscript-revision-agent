from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.ui.components.studio import empty_state, page_header, state_banner

def render(orchestrator, project_root, actor) -> None:
    page_header('Input Files', 'Local file identities, immutable hashes, and privacy-safe inventory.',
                icon=':material/upload_file:')
    state_banner(orchestrator, project_root)
    rows = orchestrator.file_inventory(project_root)
    if not rows:
        empty_state('No files registered', 'Complete project intake to create a governed inventory.'); return
    st.warning('Original inputs are never overwritten and are not offered for download from this page.',
               icon=':material/lock:')
    st.dataframe(rows, hide_index=True,
                 column_config={'size_bytes': st.column_config.NumberColumn('Size', format='%d B'),
                                'sha256': st.column_config.TextColumn('SHA-256', width='large')})
    with st.container(border=True):
        st.subheader('Privacy boundary', anchor=False)
        st.write('Only file identities and derived metadata are displayed. Full manuscript and reviewer text remain in the selected local project workspace.')
