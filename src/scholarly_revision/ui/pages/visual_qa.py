from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from scholarly_revision.models.release import MANUAL_VISUAL_QA_ARTIFACTS
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.ui.components import page_title, project_status_banner
from scholarly_revision.ui.state import redact_exception


def render(orchestrator, project_root, actor) -> None:
    page_title('Visual QA', 'Record an explicit manual decision for every required artifact.')
    project_status_banner(orchestrator, project_root)
    root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    artifacts = {
        name: root / 'outputs' / name for name in MANUAL_VISUAL_QA_ARTIFACTS
    }
    missing = [name for name, path in artifacts.items() if not path.is_file()]
    if missing:
        st.warning('Missing artifacts: ' + ', '.join(missing))
        return
    decisions = []
    with st.form('visual_qa_form'):
        maker = st.text_input('Decision maker', value=actor)
        for name, path in artifacts.items():
            st.subheader(name)
            st.code(sha256_file(path), language=None)
            opened = st.checkbox('Opened successfully', key=f'opened_{name}')
            repair = st.checkbox('Repair warning present', key=f'repair_{name}')
            layout = st.checkbox('Layout acceptable', key=f'layout_{name}')
            highlights = st.checkbox('Highlights verified', key=f'highlights_{name}')
            tables = st.checkbox(
                'Tables and captions acceptable', key=f'tables_{name}',
            )
            equivalence = st.checkbox(
                'Clean/highlighted text equivalence confirmed',
                key=f'equivalence_{name}',
            )
            notes = st.text_area('Reviewer notes', key=f'notes_{name}')
            decision = st.selectbox(
                'Explicit decision', ['REJECTED', 'APPROVED'], key=f'decision_{name}',
            )
            decisions.append({
                'artifact_name': name,
                'artifact_sha256': sha256_file(path),
                'opened_successfully': opened,
                'repair_warning_present': repair,
                'layout_acceptable': layout,
                'highlights_verified': highlights,
                'tables_and_captions_acceptable': tables,
                'clean_highlight_text_equivalence_confirmed': equivalence,
                'reviewer_notes': notes,
                'decision_maker': maker,
                'decision_timestamp': datetime.now(UTC).isoformat(),
                'decision': decision,
            })
        confirmed = st.checkbox(
            'I personally inspected every listed artifact and these decisions are explicit.',
        )
        submitted = st.form_submit_button(
            'Record visual-QA decisions',
            disabled=not allowed['record_visual_qa'],
        )
    if submitted:
        if not confirmed:
            st.error('Explicit inspection confirmation is required.')
            return
        try:
            orchestrator.record_visual_qa(
                root, {'schema_version': 1, 'decisions': decisions}, actor=actor,
            )
            st.success('Visual-QA decisions recorded and release gates reevaluated.')
            st.rerun()
        except Exception as exc:
            st.error(redact_exception(exc))
