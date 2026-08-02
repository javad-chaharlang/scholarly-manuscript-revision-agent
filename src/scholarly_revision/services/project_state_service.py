'''Validated persistent state transitions and append-only audit timeline.'''

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.project_state import (
    ProjectAuditEvent, ProjectState, ProjectStateRecord,
)


NEXT_ACTION = {
    ProjectState.NEW: 'Begin local project intake.',
    ProjectState.INTAKE_PENDING: 'Complete and validate required DOCX intake.',
    ProjectState.INTAKE_REVIEW: 'Resolve intake warnings and confirm comment boundaries.',
    ProjectState.GAP_ANALYSIS_PENDING: 'Prepare and import a source-grounded gap analysis.',
    ProjectState.PLAN_APPROVAL: 'Record an explicit decision for every revision action.',
    ProjectState.REVISION_DRAFTING: 'Prepare and import exact revision text drafts.',
    ProjectState.TEXT_APPROVAL: (
        'Approve every exact draft, then approve each reviewer-comment package '
        '(response plus linked changes).'
    ),
    ProjectState.REVISION_APPLICATION: 'Apply and verify approved text on versioned copies.',
    ProjectState.SCIENTIFIC_QA: 'Run deterministic scientific QA and resolve blockers.',
    ProjectState.RESPONSE_PREPARATION: 'Prepare, generate, and verify the response letter.',
    ProjectState.VISUAL_QA: 'Inspect every required artifact and record explicit decisions.',
    ProjectState.READY_FOR_RELEASE: 'Record final human approval and build the release package.',
    ProjectState.RELEASED: 'No action required; the immutable release is recorded.',
    ProjectState.BLOCKED: 'Resolve the listed blockers before resuming the prior state.',
}

TRANSITIONS: dict[ProjectState, set[ProjectState]] = {
    ProjectState.NEW: {ProjectState.INTAKE_PENDING},
    ProjectState.INTAKE_PENDING: {
        ProjectState.INTAKE_REVIEW, ProjectState.GAP_ANALYSIS_PENDING,
        ProjectState.BLOCKED,
    },
    ProjectState.INTAKE_REVIEW: {
        ProjectState.GAP_ANALYSIS_PENDING, ProjectState.BLOCKED,
    },
    ProjectState.GAP_ANALYSIS_PENDING: {
        ProjectState.PLAN_APPROVAL, ProjectState.BLOCKED,
    },
    ProjectState.PLAN_APPROVAL: {
        ProjectState.REVISION_DRAFTING, ProjectState.BLOCKED,
    },
    ProjectState.REVISION_DRAFTING: {
        ProjectState.TEXT_APPROVAL, ProjectState.BLOCKED,
    },
    ProjectState.TEXT_APPROVAL: {
        ProjectState.REVISION_APPLICATION, ProjectState.REVISION_DRAFTING,
        ProjectState.BLOCKED,
    },
    ProjectState.REVISION_APPLICATION: {
        ProjectState.SCIENTIFIC_QA, ProjectState.BLOCKED,
    },
    ProjectState.SCIENTIFIC_QA: {
        ProjectState.RESPONSE_PREPARATION, ProjectState.BLOCKED,
    },
    ProjectState.RESPONSE_PREPARATION: {
        ProjectState.VISUAL_QA, ProjectState.BLOCKED,
    },
    ProjectState.VISUAL_QA: {
        ProjectState.READY_FOR_RELEASE, ProjectState.BLOCKED,
    },
    ProjectState.READY_FOR_RELEASE: {
        ProjectState.RELEASED, ProjectState.VISUAL_QA,
        ProjectState.SCIENTIFIC_QA, ProjectState.BLOCKED,
    },
    ProjectState.RELEASED: set(),
    ProjectState.BLOCKED: set(ProjectState) - {
        ProjectState.NEW, ProjectState.BLOCKED, ProjectState.RELEASED,
    },
}

_PROHIBITED_DETAIL_KEYS = (
    'exact_comment', 'original_comment', 'reviewer_comment',
    'manuscript_text', 'proposed_text', 'approved_text',
    'response_text', 'content', 'secret', 'token', 'password', 'api_key',
)


def _safe_details(details: dict[str, Any] | None) -> dict[str, str | int | bool | None]:
    result: dict[str, str | int | bool | None] = {}
    for key, value in (details or {}).items():
        normalized = str(key).casefold()
        if any(term in normalized for term in _PROHIBITED_DETAIL_KEYS):
            raise ValueError(f'audit detail key is not confidentiality-safe: {key}')
        if not isinstance(value, (str, int, bool, type(None))):
            raise ValueError(f'audit detail must be scalar: {key}')
        if isinstance(value, str) and len(value) > 500:
            raise ValueError(f'audit detail is too long: {key}')
        result[str(key)] = value
    return result


class ProjectStateService:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.state_path = self.project_root / 'config' / 'project_state.json'
        self.timeline_path = self.project_root / 'audit' / 'project_timeline.jsonl'

    def _atomic_write(self, record: ProjectStateRecord) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix='project-state-', suffix='.json.tmp', dir=self.state_path.parent
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                json.dump(record.model_dump(mode='json'), stream, indent=2, sort_keys=True)
                stream.write('\n')
            os.replace(temporary, self.state_path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _append(self, event: ProjectAuditEvent) -> None:
        self.timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with self.timeline_path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(event.model_dump(mode='json'), sort_keys=True))
            stream.write('\n')

    def initialize(self, project_id: str, *, actor: str = 'system') -> ProjectStateRecord:
        if self.state_path.exists():
            raise FileExistsError(f'project state already exists: {self.state_path}')
        now = datetime.now(UTC)
        record = ProjectStateRecord(
            project_id=project_id, state=ProjectState.NEW,
            next_required_action=NEXT_ACTION[ProjectState.NEW],
            sequence=0, updated_at=now,
        )
        self._atomic_write(record)
        self._append(ProjectAuditEvent(
            sequence=0, timestamp=now, project_id=project_id,
            event_type='PROJECT_STATE_INITIALIZED', actor=actor,
            to_state=ProjectState.NEW, action='initialize',
        ))
        return record

    def load(self) -> ProjectStateRecord:
        if not self.state_path.is_file():
            raise FileNotFoundError(f'project state is missing: {self.state_path}')
        try:
            return ProjectStateRecord.model_validate_json(
                self.state_path.read_text(encoding='utf-8')
            )
        except (OSError, ValueError) as exc:
            raise ValueError(f'invalid project state: {self.state_path}') from exc

    def transition(
        self, target: ProjectState | str, *, action: str, actor: str,
        details: dict[str, Any] | None = None,
    ) -> ProjectStateRecord:
        current = self.load()
        destination = ProjectState(target)
        if destination not in TRANSITIONS[current.state]:
            raise ValueError(
                f'invalid project transition: {current.state.value} -> {destination.value}'
            )
        if current.state is ProjectState.BLOCKED and destination is not current.blocked_from:
            raise ValueError('a blocked project may resume only its recorded prior state')
        now = datetime.now(UTC)
        updated = current.model_copy(update={
            'state': destination, 'previous_state': current.state,
            'blocked_from': None, 'blockers': [],
            'next_required_action': NEXT_ACTION[destination],
            'sequence': current.sequence + 1, 'updated_at': now,
        })
        self._atomic_write(updated)
        self._append(ProjectAuditEvent(
            sequence=updated.sequence, timestamp=now,
            project_id=current.project_id, event_type='STATE_TRANSITION',
            actor=actor, from_state=current.state, to_state=destination,
            action=action, details=_safe_details(details),
        ))
        return updated

    def block(
        self, blockers: list[str], *, action: str, actor: str,
        details: dict[str, Any] | None = None,
    ) -> ProjectStateRecord:
        current = self.load()
        if current.state in {ProjectState.BLOCKED, ProjectState.RELEASED}:
            raise ValueError(f'cannot block a project in {current.state.value}')
        now = datetime.now(UTC)
        updated = current.model_copy(update={
            'state': ProjectState.BLOCKED, 'previous_state': current.state,
            'blocked_from': current.state, 'blockers': blockers,
            'next_required_action': NEXT_ACTION[ProjectState.BLOCKED],
            'sequence': current.sequence + 1, 'updated_at': now,
        })
        self._atomic_write(updated)
        self._append(ProjectAuditEvent(
            sequence=updated.sequence, timestamp=now,
            project_id=current.project_id, event_type='PROJECT_BLOCKED',
            actor=actor, from_state=current.state, to_state=ProjectState.BLOCKED,
            action=action, details=_safe_details(details),
        ))
        return updated

    def record_event(
        self, *, event_type: str, action: str, actor: str,
        details: dict[str, Any] | None = None,
    ) -> ProjectAuditEvent:
        current = self.load()
        now = datetime.now(UTC)
        updated = current.model_copy(update={
            'sequence': current.sequence + 1, 'updated_at': now,
        })
        self._atomic_write(updated)
        event = ProjectAuditEvent(
            sequence=updated.sequence, timestamp=now,
            project_id=current.project_id, event_type=event_type,
            actor=actor, from_state=current.state, to_state=current.state,
            action=action, details=_safe_details(details),
        )
        self._append(event)
        return event

    def timeline(self) -> list[ProjectAuditEvent]:
        if not self.timeline_path.is_file():
            return []
        return [
            ProjectAuditEvent.model_validate_json(line)
            for line in self.timeline_path.read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]
