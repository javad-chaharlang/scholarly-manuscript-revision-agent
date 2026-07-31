from __future__ import annotations

from pathlib import Path

import streamlit as st

from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.ui.components import download_path, page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception


def render(orchestrator, project_root, actor) -> None:
    page_title('Final Release', 'Release is refused until every mandatory gate passes.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    report_path = root / 'audit' / 'final_release_report.json'
    if report_path.is_file():
        report = read_json(report_path)
        st.metric('Evaluated readiness', report.get('readiness', 'NOT_READY'))
        st.dataframe(
            report.get('checklist', {}).get('checks', []),
            use_container_width=True, hide_index=True,
        )
        for blocker in report.get('blocker_reasons', []):
            st.error(blocker)
    allowed = orchestrator.available_actions(root)
    state = orchestrator.dashboard(root)['project_status']
    project_id = Path(root).name
    expected = f'RELEASE {project_id}'
    with st.form('final_release_form'):
        release_name = st.text_input('Release name', value='release_v001')
        maker = st.text_input('Final approver', value=actor)
        confirmation = st.text_input(f'Type exactly: {expected}')
        submitted = st.form_submit_button(
            'Approve and build immutable release',
            disabled=not allowed['final_release'],
        )
    if submitted:
        try:
            package = orchestrator.final_release(
                root, release_name=release_name, decision_maker=maker,
                confirmation=confirmation, actor=actor,
            )
            st.success(f'Release created: {package.package_path}')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
    if state == 'RELEASED':
        packages = sorted((root / 'Submission_Package').glob('release_v*'))
        for package in packages:
            st.subheader(package.name)
            for file in sorted(package.rglob('*')):
                if file.is_file():
                    download_path(
                        file, label=f'Download {file.name}',
                        key=f'download_release_{package.name}_{file.name}',
                    )
