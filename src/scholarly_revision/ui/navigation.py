'''Ordered navigation metadata and workflow-aware page availability.'''

from __future__ import annotations

from dataclasses import dataclass

from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.ui.icons import ICONS


@dataclass(frozen=True, slots=True)
class PageSpec:
    key: str
    title: str
    module: str
    group: str
    icon: str
    url_path: str
    project_required: bool = True


PAGE_SPECS = (
    PageSpec('dashboard', 'Dashboard', 'dashboard', 'Overview', ICONS['dashboard'], 'dashboard', False),
    PageSpec('projects', 'Projects', 'projects', 'Overview', ICONS['projects'], 'projects', False),
    PageSpec('new_project', 'New Project', 'new_project', 'Intake & Analysis', ICONS['new_project'], 'new-project', False),
    PageSpec('input_files', 'Input Files', 'input_files', 'Intake & Analysis', ICONS['input_files'], 'input-files'),
    PageSpec('reviewer_comments', 'Reviewer Comments', 'reviewer_comments', 'Intake & Analysis', ICONS['reviewer_comments'], 'reviewer-comments'),
    PageSpec('gap_analysis', 'Gap Analysis', 'gap_analysis', 'Intake & Analysis', ICONS['gap_analysis'], 'gap-analysis'),
    PageSpec('revision_plan', 'Revision Plan', 'revision_plan', 'Revision', ICONS['revision_plan'], 'revision-plan'),
    PageSpec('text_approval', 'Text Approval', 'text_approval', 'Revision', ICONS['text_approval'], 'text-approval'),
    PageSpec('manuscript_versions', 'Manuscript Versions', 'manuscript_versions', 'Revision', ICONS['manuscript_versions'], 'manuscript-versions'),
    PageSpec('reference_audit', 'Reference Audit', 'reference_audit', 'Quality Assurance', ICONS['reference_audit'], 'reference-audit'),
    PageSpec('scientific_qa', 'Scientific QA', 'scientific_qa', 'Quality Assurance', ICONS['scientific_qa'], 'scientific-qa'),
    PageSpec('response_letter', 'Response Letter', 'response_letter', 'Quality Assurance', ICONS['response_letter'], 'response-letter'),
    PageSpec('visual_qa', 'Visual QA', 'visual_qa', 'Quality Assurance', ICONS['visual_qa'], 'visual-qa'),
    PageSpec('final_release', 'Final Release', 'final_release', 'Release', ICONS['final_release'], 'final-release'),
    PageSpec('audit_timeline', 'Audit Timeline', 'audit_timeline', 'Release', ICONS['audit_timeline'], 'audit-timeline'),
    PageSpec('agent_tasks', 'Agent Tasks', 'agent_tasks', 'System', ICONS['agent_tasks'], 'agent-tasks'),
    PageSpec('settings', 'Settings', 'settings', 'System', ICONS['settings'], 'settings', False),
)

# Retained as the Phase 9 workflow-order compatibility surface. System
# extensions such as Agent Tasks are represented in PAGE_SPECS and the live
# navigation without changing the established workflow tuple.
NAVIGATION_ORDER = tuple(
    spec.title for spec in PAGE_SPECS if spec.key != 'agent_tasks'
)
NAVIGATION_GROUPS = tuple(dict.fromkeys(spec.group for spec in PAGE_SPECS))

STATE_ORDER = (
    ProjectState.NEW, ProjectState.INTAKE_PENDING, ProjectState.INTAKE_REVIEW,
    ProjectState.GAP_ANALYSIS_PENDING, ProjectState.PLAN_APPROVAL,
    ProjectState.REVISION_DRAFTING, ProjectState.TEXT_APPROVAL,
    ProjectState.REVISION_APPLICATION, ProjectState.SCIENTIFIC_QA,
    ProjectState.RESPONSE_PREPARATION, ProjectState.VISUAL_QA,
    ProjectState.READY_FOR_RELEASE, ProjectState.RELEASED,
)

PAGE_MIN_STATE = {
    'input_files': ProjectState.INTAKE_PENDING,
    'reviewer_comments': ProjectState.INTAKE_REVIEW,
    'gap_analysis': ProjectState.GAP_ANALYSIS_PENDING,
    'revision_plan': ProjectState.PLAN_APPROVAL,
    'text_approval': ProjectState.TEXT_APPROVAL,
    'manuscript_versions': ProjectState.REVISION_DRAFTING,
    'reference_audit': ProjectState.SCIENTIFIC_QA,
    'scientific_qa': ProjectState.SCIENTIFIC_QA,
    'response_letter': ProjectState.RESPONSE_PREPARATION,
    'visual_qa': ProjectState.VISUAL_QA,
    'final_release': ProjectState.READY_FOR_RELEASE,
    'audit_timeline': ProjectState.NEW,
    'agent_tasks': ProjectState.NEW,
}


def page_available(key: str, state: ProjectState | None, *, project_selected: bool) -> bool:
    spec = next(item for item in PAGE_SPECS if item.key == key)
    if not spec.project_required:
        return True
    if not project_selected or state is None:
        return False
    if key in {'input_files', 'audit_timeline'} or state is ProjectState.RELEASED:
        return True
    effective = state
    if state is ProjectState.BLOCKED:
        return True
    minimum = PAGE_MIN_STATE.get(key, ProjectState.NEW)
    return STATE_ORDER.index(effective) >= STATE_ORDER.index(minimum)


def navigation_state(
    active_key: str, state: ProjectState | None, *, project_selected: bool,
) -> list[dict[str, str | bool]]:
    '''Expose active and available navigation semantics for rendering and tests.'''
    return [
        {
            'key': spec.key,
            'group': spec.group,
            'active': spec.key == active_key,
            'available': page_available(
                spec.key, state, project_selected=project_selected,
            ),
        }
        for spec in PAGE_SPECS
    ]
