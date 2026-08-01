from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
import streamlit as st
from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_task import AgentTaskType
from scholarly_revision.ui.agent_controls import render_agent_task_launcher
from scholarly_revision.ui.components.studio import download, empty_state, kpis, load_json, page_header, state_banner
from scholarly_revision.ui.state import redact_exception, save_uploaded_file

def render(orchestrator, project_root, actor) -> None:
    page_header('Gap Analysis', 'Structured source-grounded coverage assessment; deterministic UI never creates semantics.',
                icon=':material/find_in_page:')
    state_banner(orchestrator, project_root); root = Path(project_root)
    allowed = orchestrator.available_actions(root)
    comment_records = load_json(root / 'working' / 'reviewer_comments.json', [])
    agent_comment_id = st.selectbox(
        'Comment for Agent gap analysis',
        [item['comment_id'] for item in comment_records],
        key='agent_gap_comment',
    ) if comment_records else None
    if agent_comment_id:
        render_agent_task_launcher(
            root, actor, task_type=AgentTaskType.GAP_ANALYSIS,
            label='Run Gap Analysis with Codex',
            purpose='Assess manuscript coverage for one exact reviewer comment.',
            key=f'agent_gap_{agent_comment_id}', comment_ids=[agent_comment_id],
            context_policy=ContextPolicy.SECTION_CONTEXT,
        )
    with st.container(horizontal=True, key='srs_action_row'):
        if st.button('Prepare analysis package', icon=':material/package_2:', disabled=not allowed['prepare_gap_analysis']):
            try: orchestrator.prepare_gap_analysis(root, actor=actor); st.success('Blank semantic package prepared.'); st.rerun()
            except Exception as exc: st.error(redact_exception(exc))
        download(root / 'working' / 'gap_analysis_template.json', 'Download package', 'gap_download')
    imported = load_json(root / 'working' / 'gap_analysis_imported.json', {'assessments': []})
    assessments = imported.get('assessments', [])
    counts = {key: sum(i.get('coverage_status') == key for i in assessments) for key in
              ('FULLY_ADDRESSED', 'PARTIALLY_ADDRESSED', 'NOT_ADDRESSED', 'CANNOT_DETERMINE')}
    kpis([(k.replace('_', ' ').title(), v, None) for k, v in counts.items()] + [
        ('Evidence required', sum(bool(i.get('required_references')) for i in assessments), None),
        ('Experiment required', sum(bool(i.get('required_experiments')) for i in assessments), None),
        ('Author decision required', sum(bool(i.get('author_decision_required')) for i in assessments), None)])
    if assessments:
        for item in assessments:
            with st.expander(f"{item['comment_id']} · {(item.get('coverage_status') or 'UNASSESSED').replace('_', ' ').title()}"):
                st.text_area('Exact comment', value=item.get('original_comment', ''), disabled=True,
                             key=f"gap_comment_{item['comment_id']}")
                for label, key in [('Manuscript evidence', 'manuscript_evidence'), ('Missing elements', 'missing_elements'),
                                   ('Required references', 'required_references'), ('Required experiments', 'required_experiments'),
                                   ('Required statistics', 'required_statistics'), ('Risks', 'risks')]:
                    st.markdown(f'**{label}:**'); st.write(item.get(key) or 'None recorded')
                st.caption(f"Confidence: {item.get('confidence')} · Manual review: {item.get('manual_review_required')}")
    else: empty_state('No imported assessment', 'Prepare, complete, and import the structured local package.')
    upload = st.file_uploader('Completed gap-analysis JSON', type=['json'], key='gap_import_upload')
    if st.button('Validate and import analysis', type='primary', icon=':material/upload:',
                 disabled=not (allowed['import_gap_analysis'] and upload)):
        try:
            with TemporaryDirectory(dir=root.parent) as temp:
                source = save_uploaded_file(upload, temp)
                orchestrator.import_gap_analysis(root, source, actor=actor)
            st.success('Analysis imported and an unapproved plan created.'); st.rerun()
        except Exception as exc: st.error(redact_exception(exc))
