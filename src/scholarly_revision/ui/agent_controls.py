'''Small contextual launchers; execution remains in the Agent Tasks workspace.'''
from __future__ import annotations
from pathlib import Path
import streamlit as st
from scholarly_revision.models.agent_context import ContextPolicy
from scholarly_revision.models.agent_task import AgentTaskType
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.ui.state import redact_exception

def render_agent_task_launcher(
    project_root: str | Path, actor: str, *, task_type: AgentTaskType,
    label: str, purpose: str, key: str, comment_ids: list[str] | None = None,
    action_ids: list[str] | None = None, element_ids: list[str] | None = None,
    context_policy: ContextPolicy | None = None,
) -> None:
    if st.button(
        label, icon=':material/smart_toy:', key=key,
        disabled=not bool(actor.strip()),
    ):
        try:
            task = AgentTaskService(project_root).create_task(
                task_type=task_type, purpose=purpose, created_by=actor,
                related_comment_ids=comment_ids or [],
                related_action_ids=action_ids or [],
                source_element_ids=element_ids or [],
                context_policy=context_policy,
            )
            st.success(
                f'{task.task_id} created. Open Agent Tasks to review context '
                'and approve transmission.'
            )
        except Exception as exc:
            st.error(redact_exception(exc))
