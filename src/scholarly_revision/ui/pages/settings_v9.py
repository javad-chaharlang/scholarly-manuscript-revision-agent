from __future__ import annotations
import streamlit as st
from scholarly_revision.ui.components.studio import page_header
from scholarly_revision.ui.i18n import LANGUAGES
from scholarly_revision.ui.layout import abbreviate_path

def render(orchestrator, project_root, actor) -> None:
    page_header('Settings', 'Local preferences, privacy boundary, and fixed repository policies.',
                icon=':material/settings:')
    st.text_input('Default decision maker', value=st.session_state.get('actor', actor), key='settings_actor')
    st.text_input('Workspace root', value=abbreviate_path(st.session_state.get('workspace_root', '')),
                  disabled=True)
    st.segmented_control('Interface language', list(LANGUAGES),
                         default='فارسی' if st.session_state.get('ui_language') == 'fa' else 'English', disabled=True)
    st.caption('Use the global language switcher in the sidebar. Persian changes UI direction only; manuscript content remains independent.')
    st.subheader('Reviewer highlight policy', anchor=False)
    st.table([{'Scope': 'Reviewer 1', 'Color': 'Yellow'},
              {'Scope': 'Reviewer 2', 'Color': 'Bright Green'},
              {'Scope': 'Shared / general', 'Color': 'Violet'}])
    st.info('Local only · No OpenAI API · No telemetry · No external HTTP calls', icon=':material/security:')
    st.caption('Theme mode is available in Streamlit settings because separate light and dark themes are configured.')
