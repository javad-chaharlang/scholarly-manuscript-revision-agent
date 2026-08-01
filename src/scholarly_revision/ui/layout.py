'''Shared application shell and workflow layout primitives.'''
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
import streamlit as st
from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.ui.i18n import t

WORKFLOW_STEPS = (
    ('Intake', 'intake', ProjectState.INTAKE_PENDING, 'input_files'),
    ('Comment Review', 'comment_review', ProjectState.INTAKE_REVIEW, 'reviewer_comments'),
    ('Gap Analysis', 'gap_analysis', ProjectState.GAP_ANALYSIS_PENDING, 'gap_analysis'),
    ('Plan Approval', 'plan_approval', ProjectState.PLAN_APPROVAL, 'revision_plan'),
    ('Drafting', 'drafting', ProjectState.REVISION_DRAFTING, 'manuscript_versions'),
    ('Text Approval', 'text_approval', ProjectState.TEXT_APPROVAL, 'text_approval'),
    ('Revision Application', 'revision_application', ProjectState.REVISION_APPLICATION, 'manuscript_versions'),
    ('Scientific QA', 'scientific_qa', ProjectState.SCIENTIFIC_QA, 'scientific_qa'),
    ('Response', 'response', ProjectState.RESPONSE_PREPARATION, 'response_letter'),
    ('Visual QA', 'visual_qa_step', ProjectState.VISUAL_QA, 'visual_qa'),
    ('Release', 'release_step', ProjectState.READY_FOR_RELEASE, 'final_release'),
)

def abbreviate_path(value: str | Path) -> str:
    path = Path(value)
    return str(path) if len(path.parts) < 4 else str(Path(path.parts[0], '...', *path.parts[-2:]))

def state_progress(state: ProjectState, blocked_from: ProjectState | None = None) -> int:
    effective = blocked_from if state is ProjectState.BLOCKED and blocked_from else state
    states = [item[2] for item in WORKFLOW_STEPS]
    if effective is ProjectState.NEW: return 0
    if effective is ProjectState.RELEASED: return 100
    return round(states.index(effective) / (len(states) - 1) * 100) if effective in states else 0

def workflow_step_states(
    record: Any | None, *, warning_steps: set[ProjectState] | None = None,
) -> list[dict[str, str | bool]]:
    '''Return all workflow stages with deterministic visual/click states.'''
    warnings = warning_steps or set()
    if record is None:
        return [
            {'label': label, 'label_key': label_key, 'state': 'pending',
             'page': page_key, 'enabled': False}
            for label, label_key, _state, page_key in WORKFLOW_STEPS
        ]
    active = record.blocked_from if record.state is ProjectState.BLOCKED else record.state
    states = [item[2] for item in WORKFLOW_STEPS]
    active_index = 0 if active is ProjectState.NEW else (
        states.index(active) if active in states else -1
    )
    result = []
    for index, (label, label_key, step_state, page_key) in enumerate(WORKFLOW_STEPS):
        status = ('complete' if record.state is ProjectState.RELEASED or index < active_index
                  else 'blocked' if index == active_index and record.state is ProjectState.BLOCKED
                  else 'warning' if index == active_index and step_state in warnings
                  else 'active' if index == active_index else 'pending')
        result.append({'label': label, 'label_key': label_key, 'state': status,
                       'page': page_key,
                       'enabled': status in {'complete', 'active', 'warning', 'blocked'}})
    return result


def quick_action_states(
    record: Any | None, *, project_selected: bool,
) -> list[dict[str, str | bool]]:
    '''Map requested dashboard shortcuts to safe workflow navigation states.'''
    state = record.state if record is not None else None
    blocked_from = record.blocked_from if state is ProjectState.BLOCKED else None
    resume_pages = {
        ProjectState.NEW: 'input_files',
        ProjectState.INTAKE_PENDING: 'input_files',
        ProjectState.INTAKE_REVIEW: 'reviewer_comments',
        ProjectState.GAP_ANALYSIS_PENDING: 'gap_analysis',
        ProjectState.PLAN_APPROVAL: 'revision_plan',
        ProjectState.REVISION_DRAFTING: 'manuscript_versions',
        ProjectState.TEXT_APPROVAL: 'text_approval',
        ProjectState.REVISION_APPLICATION: 'manuscript_versions',
        ProjectState.SCIENTIFIC_QA: 'scientific_qa',
        ProjectState.RESPONSE_PREPARATION: 'response_letter',
        ProjectState.VISUAL_QA: 'visual_qa',
        ProjectState.READY_FOR_RELEASE: 'final_release',
        ProjectState.RELEASED: 'audit_timeline',
    }
    effective = blocked_from or state
    definitions = (
        ('new_project_action', 'new_project', True),
        ('resume_project', resume_pages.get(effective, 'dashboard'), project_selected),
        ('review_comments_action', 'reviewer_comments', state is ProjectState.INTAKE_REVIEW),
        ('continue_gap', 'gap_analysis', state is ProjectState.GAP_ANALYSIS_PENDING),
        ('review_plan', 'revision_plan',
         state is ProjectState.PLAN_APPROVAL or blocked_from is ProjectState.PLAN_APPROVAL),
        ('approve_text', 'text_approval', state is ProjectState.TEXT_APPROVAL),
        ('run_qa', 'scientific_qa', state is ProjectState.SCIENTIFIC_QA),
        ('prepare_response', 'response_letter', state is ProjectState.RESPONSE_PREPARATION),
        ('complete_visual_qa', 'visual_qa',
         state is ProjectState.VISUAL_QA or blocked_from is ProjectState.VISUAL_QA),
        ('build_release', 'final_release', state is ProjectState.READY_FOR_RELEASE),
    )
    return [
        {'label_key': label_key, 'page': page, 'enabled': enabled}
        for label_key, page, enabled in definitions
    ]
