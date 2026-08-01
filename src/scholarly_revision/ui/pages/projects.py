from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.ui.components.studio import empty_state, page_header
from scholarly_revision.ui.layout import state_progress
from scholarly_revision.ui.state import set_active_project

def render(orchestrator, project_root, actor) -> None:
    page_header('Projects', 'Search and resume confidential projects registered in this workspace.',
                icon=':material/folder_managed:')
    if orchestrator is None:
        empty_state('Choose a workspace root', 'The portfolio is stored locally outside Git.')
        return
    show_archived = st.toggle('Include archived projects', value=False)
    projects = orchestrator.registry.list_projects(include_archived=show_archived)
    if not projects:
        empty_state('No projects yet', 'Use New Project to create the first revision workspace.')
        return
    query = st.text_input('Search projects', placeholder='Project name or manuscript ID',
                          icon=':material/search:')
    states = sorted({item.state.value for item in projects})
    state_filter = st.multiselect('Workflow state', states)
    journal_filter = st.multiselect(
        'Journal',
        sorted({
            load_project_manifest(Path(item.project_root) / 'config' / 'project_manifest.yaml').journal
            for item in projects
        }),
    )
    readiness_filter = st.multiselect(
        'Release readiness', ['BLOCKED', 'NOT_READY', 'READY_WITH_WARNINGS', 'READY', 'NOT_EVALUATED'],
    )
    sort_by = st.selectbox('Sort by', ['Last modified (newest)', 'Project name'])
    view = st.segmented_control('View', ['Cards', 'Table'], default='Cards')
    rows = []
    for item in projects:
        if query and query.casefold() not in f'{item.project_name} {item.manuscript_id}'.casefold(): continue
        if state_filter and item.state.value not in state_filter: continue
        root = Path(item.project_root)
        manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
        record = ProjectStateService(root).load()
        status = orchestrator.dashboard(root)
        if journal_filter and manifest.journal not in journal_filter: continue
        if readiness_filter and status['release_readiness'] not in readiness_filter: continue
        rows.append((item, manifest, record, status))
    if sort_by == 'Project name':
        rows.sort(key=lambda row: row[0].project_name.casefold())
    if view == 'Table':
        st.dataframe([{'Project': i.project_name, 'Manuscript ID': i.manuscript_id,
                       'Journal': m.journal, 'State': r.state.value,
                       'Progress': state_progress(r.state, r.blocked_from),
                       'Comments': s['total_comments'], 'Blockers': len(s['blockers']),
                       'Next action': s['next_recommended_action'], 'Last modified': i.updated_at}
                      for i, m, r, s in rows], hide_index=True,
                     column_config={'Progress': st.column_config.ProgressColumn(min_value=0, max_value=100)})
    else:
        for item, manifest, record, status in rows:
            with st.container(border=True):
                st.subheader(item.project_name, anchor=False)
                st.caption(f'{item.manuscript_id} · {manifest.journal} · {record.state.value}')
                if item.archived:
                    st.warning('Archived - the project files remain unchanged.')
                st.progress(state_progress(record.state, record.blocked_from))
                st.write(status['next_recommended_action'])
                with st.container(horizontal=True):
                    if st.button('Open / resume', icon=':material/play_arrow:',
                                 disabled=item.archived, key=f'open_{item.project_id}'):
                        set_active_project(st.session_state, project_id=item.project_id,
                                           project_root=item.project_root)
                        st.rerun()
                    if item.archived:
                        if st.button('Restore', icon=':material/unarchive:', key=f'restore_{item.project_id}'):
                            orchestrator.registry.set_archived(item.project_id, archived=False)
                            st.success('Project restored. No project files were changed.')
                            st.rerun()
                    else:
                        with st.popover('Archive', icon=':material/archive:'):
                            st.warning('This hides the registry entry. It never deletes project files.')
                            expected = f'ARCHIVE {item.project_id}'
                            confirmation = st.text_input(
                                f'Type {expected} to confirm', key=f'archive_confirm_{item.project_id}',
                            )
                            if st.button('Confirm archive', type='primary',
                                         disabled=confirmation != expected,
                                         key=f'archive_submit_{item.project_id}'):
                                orchestrator.registry.set_archived(item.project_id, archived=True)
                                st.success('Project archived. Its confidential files remain in place.')
                                st.rerun()
