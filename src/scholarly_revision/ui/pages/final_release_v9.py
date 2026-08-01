from __future__ import annotations
from pathlib import Path
import zipfile
from io import BytesIO
import streamlit as st
from scholarly_revision.ui.components.studio import banner, download, empty_state, page_header, state_banner
from scholarly_revision.ui.project_data import release_report
from scholarly_revision.ui.state import redact_exception

def _zip_package(path: Path) -> bytes:
    data = BytesIO()
    with zipfile.ZipFile(data, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(path.rglob('*')):
            if file.is_file(): archive.write(file, file.relative_to(path).as_posix())
    return data.getvalue()

def render(orchestrator, project_root, actor) -> None:
    page_header('Final Release', 'Release-control dashboard: every mandatory gate remains authoritative.',
                icon=':material/rocket_launch:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    report = release_report(root)
    readiness = report.get('readiness', 'NOT_READY')
    st.badge(readiness.replace('_', ' ').title(), color='green' if readiness == 'READY' else 'red' if readiness == 'BLOCKED' else 'orange')
    checks = report.get('checklist', {}).get('checks', [])
    if checks:
        st.dataframe(checks, hide_index=True,
                     column_config={'passed': st.column_config.CheckboxColumn('Passed', disabled=True)})
    else: empty_state('Release checklist not evaluated', 'Complete response and visual QA to run final consistency checks.')
    blockers = report.get('blocker_reasons', [])
    warnings = report.get('warnings', [])
    if blockers: banner('blocker', '\n'.join(blockers))
    if warnings: banner('warning', '\n'.join(warnings))
    allowed = orchestrator.available_actions(root); project_id = root.name
    with st.form('release_v9', border=True):
        release_name = st.text_input('Immutable release name', value='release_v001')
        maker = st.text_input('Final approver', value=actor)
        confirmation = st.text_input(f'Type exactly: RELEASE {project_id}')
        acknowledged = st.checkbox('I approve this exact evaluated artifact set for final release.')
        submitted = st.form_submit_button('Build immutable release', type='primary',
            disabled=not allowed['final_release'] or not acknowledged or confirmation != f'RELEASE {project_id}')
    if submitted:
        try:
            with st.status('Revalidating gates and building immutable package...', expanded=True):
                orchestrator.final_release(root, release_name=release_name, decision_maker=maker,
                                           confirmation=confirmation, actor=actor)
            st.success('Immutable release created.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
    packages = sorted((root / 'Submission_Package').glob('release_v*')) if (root / 'Submission_Package').is_dir() else []
    for package in packages:
        with st.expander(package.name):
            for file in sorted(package.rglob('*')):
                if file.is_file(): download(file, f'Download {file.name}', f'release_{package.name}_{file.name}')
            st.download_button('Download complete ZIP', _zip_package(package),
                               file_name=f'{package.name}.zip', mime='application/zip',
                               icon=':material/folder_zip:', key=f'zip_{package.name}')
