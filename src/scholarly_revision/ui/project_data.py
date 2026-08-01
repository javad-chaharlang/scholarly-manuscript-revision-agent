'''Read-only, confidentiality-conscious project metadata loaders for the UI.'''
from __future__ import annotations
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from scholarly_revision.models.project_state import ProjectState
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.ui.layout import state_progress

def json_or(path: Path, default: Any) -> Any:
    try:
        return read_json(path) if path.is_file() else default
    except (OSError, ValueError):
        return default

def project_snapshot(project_root: str | Path, orchestrator: Any) -> dict[str, Any]:
    root = Path(project_root)
    manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
    record = ProjectStateService(root).load()
    base = orchestrator.dashboard(root)
    comments = json_or(root / 'working' / 'reviewer_comments.json', [])
    plan = json_or(root / 'working' / 'revision_plan.json', {'actions': []})
    gaps = json_or(root / 'working' / 'gap_analysis_imported.json', {'assessments': []})
    qa = json_or(root / 'audit' / 'scientific_qa_report.json', {'issues': []})
    response = json_or(root / 'working' / 'response_package.json', {'sections': []})
    actions = plan.get('actions', [])
    assessments = gaps.get('assessments', [])
    issues = qa.get('issues', [])
    entries = [entry for section in response.get('sections', []) for entry in section.get('entries', [])]
    verified_comments = sum(item.get('status') == 'VERIFIED' for item in comments)
    pending_actions = sum(item.get('status') not in {'APPLIED', 'VERIFIED', 'NOT_APPLICABLE'} for item in actions)
    evidence_items = sum(item.get('evidence_status') in {'REQUIRED', 'MISSING'} for item in comments)
    snapshot = {
        **base, 'manifest': manifest, 'state_record': record,
        'comments': comments, 'actions': actions, 'assessments': assessments,
        'issues': issues, 'response_entries': entries,
        'verified_comments': verified_comments, 'pending_actions': pending_actions,
        'evidence_dependent': evidence_items,
        'progress': state_progress(record.state, record.blocked_from),
        'last_modified': datetime.fromtimestamp(root.stat().st_mtime).astimezone(),
        'comments_by_status': dict(Counter(item.get('status', 'UNKNOWN') for item in comments)),
        'priority_distribution': dict(Counter(item.get('priority', 'UNKNOWN') for item in comments)),
        'actions_by_approval': dict(Counter(item.get('approval_state', 'UNKNOWN') for item in actions)),
        'qa_by_severity': dict(Counter(item.get('severity', 'UNKNOWN') for item in issues)),
    }
    return snapshot

def read_versions(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root)
    payload = json_or(root / 'audit' / 'document_version_manifest.json', {'versions': []})
    return payload.get('versions', [])

def release_report(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    for path in (root / 'audit' / 'final_release_report.json', root / 'outputs' / 'Final_Release_Report.json'):
        if path.is_file():
            return json_or(path, {})
    return {}


def recent_project_snapshots(orchestrator: Any | None, *, limit: int = 4) -> list[dict[str, Any]]:
    '''Return confidentiality-safe registry metadata for dashboard cards.'''
    if orchestrator is None:
        return []
    rows: list[dict[str, Any]] = []
    for entry in orchestrator.registry.list_projects()[:limit]:
        root = Path(entry.project_root)
        try:
            manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
            record = ProjectStateService(root).load()
            status = orchestrator.dashboard(root)
        except (OSError, ValueError):
            continue
        rows.append({
            'project_id': entry.project_id,
            'project_name': entry.project_name,
            'project_root': entry.project_root,
            'manuscript_id': entry.manuscript_id,
            'journal': manifest.journal,
            'state': record.state.value,
            'progress': state_progress(record.state, record.blocked_from),
            'blocker_count': len(status.get('blockers') or []),
            'readiness': str(status.get('release_readiness', 'NOT_EVALUATED')),
            'last_modified': entry.updated_at,
        })
    return rows
