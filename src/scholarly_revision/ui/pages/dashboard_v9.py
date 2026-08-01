from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from scholarly_revision.ui.components.studio import banner, kpis
from scholarly_revision.ui.i18n import status_label, t
from scholarly_revision.ui.layout import quick_action_states
from scholarly_revision.ui.project_data import project_snapshot, recent_project_snapshots
from scholarly_revision.ui.state import set_active_project


try:
    APPLICATION_VERSION = version('scholarly-manuscript-revision-agent')
except PackageNotFoundError:
    APPLICATION_VERSION = '0.4.0'


ACTION_ICONS = {
    'new_project_action': ':material/create_new_folder:',
    'resume_project': ':material/play_arrow:',
    'review_comments_action': ':material/rate_review:',
    'continue_gap': ':material/find_in_page:',
    'review_plan': ':material/task_alt:',
    'approve_text': ':material/approval:',
    'run_qa': ':material/fact_check:',
    'prepare_response': ':material/draft:',
    'complete_visual_qa': ':material/visibility:',
    'build_release': ':material/rocket_launch:',
}


def _quick_actions(record: Any | None, page_handles: Mapping[str, Any], *, selected: bool) -> None:
    st.subheader(t('quick_actions', st.session_state), anchor=False)
    st.caption(t('valid_actions_hint', st.session_state))
    with st.container(horizontal=True, key='srs_action_row'):
        for item in quick_action_states(record, project_selected=selected):
            label_key = str(item['label_key'])
            page = page_handles.get(str(item['page']))
            enabled = bool(item['enabled']) and page is not None
            if st.button(
                t(label_key, st.session_state),
                icon=ACTION_ICONS[label_key],
                type='primary' if label_key == 'new_project_action' else 'secondary',
                disabled=not enabled,
                key=f'quick_{label_key}',
            ):
                st.switch_page(page)


def _recent_projects(orchestrator: Any | None) -> None:
    st.subheader(t('recent_projects', st.session_state), anchor=False)
    st.caption(t('last_opened_projects', st.session_state))
    rows = recent_project_snapshots(orchestrator)
    if not rows:
        with st.container(border=True, key='srs_recent_empty'):
            st.markdown('### :material/history: ' + t('no_recent_projects', st.session_state))
            st.caption(t('getting_started_hint', st.session_state))
        return
    with st.container(horizontal=True, key='srs_recent_grid'):
        for row in rows:
            with st.container(border=True, width='stretch'):
                project_name = row['project_name']
                manuscript_id = row['manuscript_id']
                journal = row['journal']
                st.markdown(f'**{project_name}**')
                manuscript_label = t('manuscript_id', st.session_state)
                journal_label = t('journal', st.session_state)
                identity = (
                    f'{manuscript_label}: {manuscript_id} | '
                    f'{journal_label}: {journal}'
                )
                st.caption(identity)
                st.badge(status_label(row['state'], st.session_state), color='blue')
                readiness = str(row['readiness'])
                st.badge(
                    status_label(readiness, st.session_state),
                    color='green' if readiness == 'READY' else 'orange',
                )
                progress = int(row['progress'])
                completion_label = t('completion', st.session_state)
                st.progress(
                    progress,
                    text=f'{completion_label} | {progress}%',
                )
                blocker_count = row['blocker_count']
                modified = row['last_modified']
                blocker_label = t('blockers', st.session_state)
                modified_label = t('last_modified', st.session_state)
                st.caption(
                    f'{blocker_label}: {blocker_count} | '
                    f'{modified_label}: {modified:%Y-%m-%d %H:%M}'
                )
                project_id = str(row['project_id'])
                if st.button(
                    t('resume', st.session_state),
                    icon=':material/play_arrow:',
                    key=f'resume_{project_id}',
                ):
                    set_active_project(
                        st.session_state,
                        project_id=project_id,
                        project_root=str(row['project_root']),
                    )
                    st.rerun()


def _getting_started() -> None:
    st.subheader(t('getting_started', st.session_state), anchor=False)
    steps = (
        ('looks_one', 'select_workspace'),
        ('looks_two', 'upload_inputs'),
        ('looks_3', 'review_comments'),
    )
    with st.container(horizontal=True, key='srs_getting_started'):
        for icon, key in steps:
            with st.container(border=True, width='stretch'):
                st.markdown(f'### :material/{icon}: {t(key, st.session_state)}')


def _required_inputs() -> None:
    with st.container(border=True, height='stretch'):
        st.subheader(t('required_inputs', st.session_state), anchor=False)
        pending_label = t('pending', st.session_state)
        for key in (
            'manuscript_file', 'reviewer_files', 'project_manifest',
            'journal_instructions', 'verified_references',
            'experimental_records', 'author_approvals',
        ):
            st.markdown(
                f':material/radio_button_unchecked: {t(key, st.session_state)} '
                f'| :gray[{pending_label}]'
            )


def _system_readiness(orchestrator: Any | None, actor: str) -> None:
    with st.container(border=True, height='stretch'):
        st.subheader(t('system_readiness', st.session_state), anchor=False)
        workspace_ready = orchestrator is not None
        st.metric(
            t('workspace_status', st.session_state),
            t('configured' if workspace_ready else 'not_configured', st.session_state),
            border=True,
        )
        project_count = len(orchestrator.registry.list_projects()) if workspace_ready else 0
        st.metric(t('registry_status', st.session_state), project_count, border=True)
        st.badge(
            t('local_only', st.session_state),
            icon=':material/computer:', color='green',
        )
        st.badge(
            t('telemetry_off', st.session_state),
            icon=':material/shield:', color='green',
        )
        decision_maker = actor or '—'
        decision_label = t('decision_maker', st.session_state)
        version_label = t('application_version', st.session_state)
        st.caption(
            f'{decision_label}: {decision_maker} | '
            f'{version_label}: {APPLICATION_VERSION}'
        )


def _chart(title: str, values: dict[str, int]) -> None:
    with st.container(border=True):
        st.subheader(title, anchor=False)
        if values:
            frame = pd.DataFrame({'Category': list(values), 'Count': list(values.values())})
            st.bar_chart(frame, x='Category', y='Count')
        else:
            st.caption(t('no_chart_records', st.session_state))


def render(
    orchestrator: Any | None, project_root: str | None, actor: str,
    *, page_handles: Mapping[str, Any] | None = None,
) -> None:
    handles = page_handles or {}
    if not project_root or orchestrator is None:
        _quick_actions(None, handles, selected=False)
        _getting_started()
        _recent_projects(orchestrator)
        st.subheader(t('workflow_overview', st.session_state), anchor=False)
        with st.container(border=True):
            st.markdown(
                ':material/account_tree: '
                + t('value_proposition', st.session_state)
            )
            st.caption(t('valid_actions_hint', st.session_state))
        left, right = st.columns(2)
        with left:
            _required_inputs()
        with right:
            _system_readiness(orchestrator, actor)
        return

    data = project_snapshot(project_root, orchestrator)
    record = data['state_record']
    _quick_actions(record, handles, selected=True)
    kpis([
        (t('total_comments', st.session_state), data['total_comments'], None),
        (t('verified_comments', st.session_state), data['verified_comments'], None),
        (t('pending_actions', st.session_state), data['pending_actions'], None),
        (t('evidence_dependent', st.session_state), data['evidence_dependent'], None),
        (t('open_qa_blockers', st.session_state), data['qa_blockers'], None),
        (t('verified_responses', st.session_state), data['verified_responses'], None),
        (t('release_readiness', st.session_state), data['release_readiness'], None),
    ])
    next_recommended = data['next_recommended_action']
    next_action_label = t('next_action', st.session_state)
    banner(
        'blocker' if data['blockers'] else 'information',
        '; '.join(data['blockers']) if data['blockers']
        else f'{next_action_label}: {next_recommended}',
    )
    left, right = st.columns(2)
    with left:
        _chart(t('comments_by_reviewer', st.session_state), data['comments_by_reviewer'])
        _chart(t('priority_distribution', st.session_state), data['priority_distribution'])
    with right:
        _chart(t('comments_by_status', st.session_state), data['comments_by_status'])
        _chart(t('actions_by_approval', st.session_state), data['actions_by_approval'])
    with st.container(border=True):
        st.subheader(t('open_blockers_manual', st.session_state), anchor=False)
        manual = [
            item for item in data['comments']
            if item.get('manual_review_required')
        ]
        if data['blockers']:
            for blocker in data['blockers']:
                st.error(blocker)
        if manual:
            st.dataframe([
                {
                    'Comment ID': item.get('comment_id'),
                    'Priority': item.get('priority'),
                    'Status': item.get('status'),
                }
                for item in manual
            ], hide_index=True)
        if not data['blockers'] and not manual:
            st.success(t('no_current_blocker', st.session_state))
    _recent_projects(orchestrator)
