from __future__ import annotations

import streamlit as st

from scholarly_revision.ui.components import page_title, project_status_banner


def render(orchestrator, project_root, actor) -> None:
    page_title('Input Files', 'Local file identities only; source text is not logged.')
    project_status_banner(orchestrator, project_root)
    st.warning('Original inputs are never overwritten and are not offered for download here.')
    st.dataframe(
        orchestrator.file_inventory(project_root),
        use_container_width=True, hide_index=True,
    )
