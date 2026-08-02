'''Minimal, redacted, author-reviewable context package construction.'''
from __future__ import annotations
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from scholarly_revision.models.agent_context import (
    AgentContextManifest, ContextManuscriptSection, ContextPolicy,
    ContextReviewerComment,
)
from scholarly_revision.models.agent_task import AgentTask, AgentTaskType
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.gap_analysis_service import read_json
from scholarly_revision.services.project_workspace import sha256_file

_SENSITIVE_KEYS = re.compile(
    r'author_?email|e-?mail|phone|address|private_?notes?|journal_?login|'
    r'api_?key|token|secret|password|credential', re.I,
)
_PATTERNS = (
    ('author email', re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')),
    ('phone number', re.compile(r'(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)')),
    ('local absolute path', re.compile(r'(?i)(?<!\w)[A-Z]:\\[^\r\n\t<>|]+')),
    ('local absolute path', re.compile(r'(?<!\w)/(?:home|users|mnt|var|tmp)/[^\s<>|]+')),
    ('API key or token', re.compile(r'(?i)\b(?:sk-[\w-]{12,}|bearer\s+[\w.-]{12,})\b')),
)

def redact_sensitive(value: Any) -> tuple[Any, list[str]]:
    redactions: list[str] = []
    def visit(item: Any, key: str = '') -> Any:
        if _SENSITIVE_KEYS.search(key):
            redactions.append(f'sensitive field removed: {key}')
            return '[REDACTED]'
        if isinstance(item, dict):
            return {str(k): visit(v, str(k)) for k, v in item.items()}
        if isinstance(item, list):
            return [visit(nested) for nested in item]
        if not isinstance(item, str):
            return item
        for label, pattern in _PATTERNS:
            item, count = pattern.subn('[REDACTED]', item)
            if count:
                redactions.append(f'{label} redacted')
        return item
    return visit(value), list(dict.fromkeys(redactions))

def _json_or(path: Path, default: Any) -> Any:
    return read_json(path) if path.is_file() else default

def _registry(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ('records', 'results', 'references', 'evidence'):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []

class AgentContextService:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()

    def _sources(self) -> dict[str, Path]:
        manifest = load_project_manifest(self.root / 'config' / 'project_manifest.yaml')
        files = {
            'reviewer_comments': self.root / 'working' / 'reviewer_comments.json',
            'manuscript_structure': self.root / 'working' / 'manuscript_structure.json',
            'evidence_records': self.root / 'working' / 'evidence_records.json',
        }
        if manifest.input_files.result_registry:
            files['result_registry'] = self.root / 'input' / manifest.input_files.result_registry
        if manifest.input_files.reference_registry:
            files['reference_registry'] = self.root / 'input' / manifest.input_files.reference_registry
        return files

    def prepare(
        self, task: AgentTask, *, custom_payload: dict[str, Any] | None = None,
        custom_context_author_approved: bool = False,
    ) -> AgentContextManifest:
        policy = ContextPolicy(task.context_policy)
        if policy is ContextPolicy.CUSTOM_AUTHOR_APPROVED_CONTEXT and (
            not custom_context_author_approved or custom_payload is None
        ):
            raise ValueError('custom context requires an explicit author-approved payload')
        sources = self._sources()
        plan_path = self.root / 'working' / 'revision_plan.json'
        raw_comments = _json_or(sources['reviewer_comments'], [])
        by_comment = {
            str(item.get('comment_id')): item for item in raw_comments
            if isinstance(item, dict)
        }
        unknown = sorted(set(task.related_comment_ids) - set(by_comment))
        if unknown:
            raise ValueError('unknown context comment IDs: ' + ', '.join(unknown))
        comments = [
            ContextReviewerComment(
                comment_id=comment_id,
                exact_comment=str(by_comment[comment_id]['original_comment']),
            ) for comment_id in task.related_comment_ids
        ]
        structure = _json_or(sources['manuscript_structure'], {'elements': []})
        elements = structure.get('elements', []) if isinstance(structure, dict) else []
        by_element: dict[str, dict[str, Any]] = {}
        for item in elements:
            if not isinstance(item, dict):
                continue
            for key in ('element_id', 'paragraph_id'):
                if item.get(key):
                    by_element[str(item[key])] = item
        requested = list(task.source_element_ids)
        if policy is ContextPolicy.EXTENDED_SECTION_CONTEXT and requested:
            expanded = list(requested)
            for element_id in requested:
                target = by_element.get(element_id)
                if target is None:
                    continue
                index = elements.index(target)
                for item in elements[max(0, index - 1):index + 2]:
                    identifier = item.get('paragraph_id') or item.get('element_id')
                    if identifier:
                        expanded.append(str(identifier))
            requested = list(dict.fromkeys(expanded))
        unknown_elements = sorted(set(requested) - set(by_element))
        if unknown_elements:
            raise ValueError('unknown context element IDs: ' + ', '.join(unknown_elements))
        chosen = [by_element[value] for value in requested]
        sections: dict[str, dict[str, list[str]]] = {}
        for item in chosen:
            section = str(item.get('section') or item.get('section_path') or 'UNSPECIFIED')
            record = sections.setdefault(section, {'paragraph_ids': [], 'excerpts': []})
            record['paragraph_ids'].append(
                str(item.get('paragraph_id') or item.get('element_id'))
            )
            record['excerpts'].append(str(item.get('text') or ''))
        section_records = [
            ContextManuscriptSection(section=name, **values)
            for name, values in sections.items()
        ]
        evidence = _registry(sources.get('evidence_records'))
        plan = _json_or(plan_path, {'actions': []})
        requested_actions = {
            str(item.get('action_id')): item for item in plan.get('actions', [])
            if isinstance(item, dict) and item.get('action_id')
        }
        unknown_actions = sorted(set(task.related_action_ids) - set(requested_actions))
        if unknown_actions:
            raise ValueError('unknown context action IDs: ' + ', '.join(unknown_actions))
        actions = [requested_actions[value] for value in task.related_action_ids]
        draft_template_path = self.root / 'working' / 'revision_draft_template.json'
        draft_template = _json_or(draft_template_path, {'drafts': []})
        prepared_drafts = [
            item for item in draft_template.get('drafts', [])
            if isinstance(item, dict) and item.get('action_id') in task.related_action_ids
        ]
        results = _registry(sources.get('result_registry'))
        references = _registry(sources.get('reference_registry'))
        if policy not in {
            ContextPolicy.RESULTS_CONTEXT, ContextPolicy.RESPONSE_CONTEXT,
            ContextPolicy.CUSTOM_AUTHOR_APPROVED_CONTEXT,
        }:
            results = []
        if policy not in {
            ContextPolicy.REFERENCE_CONTEXT, ContextPolicy.RESPONSE_CONTEXT,
            ContextPolicy.CUSTOM_AUTHOR_APPROVED_CONTEXT,
        }:
            references = []
        if policy is ContextPolicy.MINIMAL_COMMENT_CONTEXT:
            section_records, chosen, evidence = [], [], []
        traceability: dict[str, Any] = {}
        if policy is ContextPolicy.RESPONSE_CONTEXT:
            plan = _json_or(self.root / 'working' / 'revision_plan.json', {'actions': []})
            changes = _json_or(self.root / 'audit' / 'change_log.json', {'changes': []})
            action_ids = set(task.related_action_ids)
            if task.task_type is AgentTaskType.PREAPPLICATION_RESPONSE_DRAFT:
                preapplication_path = self.root / 'working' / 'comment_approval_working.json'
                if not preapplication_path.is_file():
                    preapplication_path = self.root / 'working' / 'comment_approval_template.json'
                response_input = _json_or(preapplication_path, {'records': []})
                response_values = response_input.get('records', [])
            else:
                response_input = _json_or(
                    self.root / 'working' / 'response_drafting_package.json',
                    {'entries': []},
                )
                response_values = response_input.get('entries', [])
            response_entries = [
                item for item in response_values
                if isinstance(item, dict)
                and item.get('comment_id') in task.related_comment_ids
            ]
            evidence_ids = {
                str(value) for item in response_entries
                for value in item.get('related_evidence_ids', [])
            }
            reference_ids = {
                str(value) for item in response_entries
                for value in item.get('related_reference_ids', [])
            }
            result_ids = {
                str(value) for item in response_entries
                for value in item.get('related_result_ids', [])
            }
            evidence = [
                item for item in evidence
                if str(item.get('evidence_id')) in evidence_ids
            ]
            references = [
                item for item in references
                if str(item.get('reference_id')) in reference_ids
            ]
            results = [
                item for item in results
                if str(item.get('result_id')) in result_ids
            ]
            traceability = {
                'actions': [
                    item for item in plan.get('actions', [])
                    if item.get('action_id') in action_ids
                ],
                'verified_changes': [
                    item for item in changes.get('changes', [])
                    if item.get('action_id') in action_ids
                    and item.get('verification_status') == 'VERIFIED'
                ],
                'response_records': response_entries,
            }
        payload: dict[str, Any] = custom_payload if custom_payload is not None else {
            'reviewer_comments': [item.model_dump(mode='json') for item in comments],
            'manuscript_sections': [item.model_dump(mode='json') for item in section_records],
            'evidence_records': evidence,
            'revision_actions': actions,
            'prepared_drafts': prepared_drafts,
            'result_records': results,
            'references': references,
            'traceability': traceability,
        }
        redacted, redactions = redact_sensitive(payload)
        if not isinstance(redacted, dict):
            raise ValueError('context payload must be a JSON object')
        serialized = json.dumps(
            redacted, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        )
        included_paths = [
            path for key, path in sources.items()
            if path.is_file() and (
                key in {'reviewer_comments', 'manuscript_structure'}
                or key == 'result_registry' and results
                or key == 'reference_registry' and references
                or key == 'evidence_records' and evidence
            )
        ]
        if actions and plan_path.is_file():
            included_paths.append(plan_path)
        if prepared_drafts and draft_template_path.is_file():
            included_paths.append(draft_template_path)
        hashes = {
            path.relative_to(self.root).as_posix(): sha256_file(path)
            for path in included_paths
        }
        exclusions = [
            'Unrelated manuscript sections',
            'Author personal information unless required',
            'Hidden document metadata',
            'API credentials and authentication tokens',
            'Original experimental datasets',
            'Unapproved confidential attachments',
        ]
        return AgentContextManifest(
            context_id=f'CTX-{uuid4().hex[:12].upper()}',
            task_id=task.task_id, project_id=task.project_id,
            context_policy=policy, prepared_at=datetime.now(UTC),
            reviewer_comments_included=comments,
            manuscript_sections_included=section_records,
            paragraph_ids_included=[
                str(item.get('paragraph_id') or item.get('element_id')) for item in chosen
            ],
            evidence_records_included=evidence,
            result_records_included=results,
            references_included=references,
            exclusions=exclusions, redactions=redactions,
            total_character_count=len(serialized),
            input_file_hashes=hashes, transmitted_payload=redacted,
            custom_context_author_approved=custom_context_author_approved,
        )
