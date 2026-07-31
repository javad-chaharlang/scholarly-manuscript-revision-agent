from __future__ import annotations

import streamlit as st

from scholarly_revision.ui.components import page_title


def render(orchestrator, project_root, actor) -> None:
    page_title('Settings', 'Local runtime settings; secrets are neither required nor displayed.')
    st.session_state['actor'] = st.text_input(
        'Default decision maker', value=st.session_state.get('actor', actor),
    )
    st.text_input(
        'Workspace root', value=st.session_state.get('workspace_root', ''),
        disabled=True,
    )
    st.text_input('Registry file', value=str(orchestrator.registry.path), disabled=True)
    st.subheader('Required highlight policy')
    st.table([
        {'scope': 'Reviewer 1', 'color': 'Yellow'},
        {'scope': 'Reviewer 2', 'color': 'Bright Green'},
        {'scope': 'Shared/general', 'color': 'Violet'},
    ])
    st.info('The application runs locally and does not use the OpenAI API.')
