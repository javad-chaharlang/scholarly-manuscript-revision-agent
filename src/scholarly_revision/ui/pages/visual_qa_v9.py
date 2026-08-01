from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path
import streamlit as st
from scholarly_revision.models.release import MANUAL_VISUAL_QA_ARTIFACTS
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.ui.components.studio import banner, page_header, state_banner
from scholarly_revision.ui.state import redact_exception

def render(orchestrator, project_root, actor) -> None:
    page_header('Visual QA', 'Explicit human inspection of every required deliverable.',
                icon=':material/visibility:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    artifacts = {name: root / 'outputs' / name for name in MANUAL_VISUAL_QA_ARTIFACTS}
    missing = [name for name, path in artifacts.items() if not path.is_file()]
    if missing:
        banner('blocker', 'MANUAL_VISUAL_QA_REQUIRED · Missing artifacts: ' + ', '.join(missing)); return
    banner('warning', 'MANUAL_VISUAL_QA_REQUIRED remains active until every current artifact has an explicit decision.')
    allowed = orchestrator.available_actions(root); decisions = []
    with st.form('visual_qa_v9', border=False):
        maker = st.text_input('Decision maker', value=actor)
        for name, path in artifacts.items():
            with st.container(border=True):
                st.subheader(name, anchor=False); st.code(sha256_file(path), language=None)
                opened = st.checkbox('Opened successfully', key=f'v9_opened_{name}')
                repair = st.checkbox('Repair warning present', key=f'v9_repair_{name}')
                layout = st.checkbox('Layout acceptable', key=f'v9_layout_{name}')
                highlights = st.checkbox('Highlights verified', key=f'v9_highlights_{name}')
                tables = st.checkbox('Tables and captions acceptable', key=f'v9_tables_{name}')
                equivalence = st.checkbox('Text equivalence confirmed', key=f'v9_equiv_{name}')
                notes = st.text_area('Inspection notes', key=f'v9_notes_{name}')
                decision = st.segmented_control('Explicit decision', ['REJECTED', 'APPROVED'],
                                                default='REJECTED', key=f'v9_decision_{name}')
                decisions.append({'artifact_name': name, 'artifact_sha256': sha256_file(path),
                    'opened_successfully': opened, 'repair_warning_present': repair,
                    'layout_acceptable': layout, 'highlights_verified': highlights,
                    'tables_and_captions_acceptable': tables,
                    'clean_highlight_text_equivalence_confirmed': equivalence,
                    'reviewer_notes': notes, 'decision_maker': maker,
                    'decision_timestamp': datetime.now(UTC).isoformat(), 'decision': decision})
        confirmed = st.checkbox('I personally inspected every artifact and explicitly recorded these decisions.')
        submitted = st.form_submit_button('Record visual-QA decisions', type='primary',
                                          disabled=not allowed['record_visual_qa'] or not confirmed)
    if submitted:
        try:
            orchestrator.record_visual_qa(root, {'schema_version': 1, 'decisions': decisions}, actor=actor)
            st.success('Visual decisions saved; release consistency was reevaluated.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
