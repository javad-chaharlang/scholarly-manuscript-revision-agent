'''Safe, deterministic YAML loading for project manifests.'''

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scholarly_revision.models.project import ProjectManifest


_NESTED_TOP_LEVEL_FIELDS = {
    'project',
    'languages',
    'citation_style',
    'reviewer_count',
    'result_status',
    'highlight_policy',
    'approval_gates',
    'input_files',
    'output_names',
    'created_at',
    'updated_at',
}
_PROJECT_FIELDS = {
    'name',
    'manuscript_id',
    'manuscript_title',
    'journal',
    'revision_round',
}
_LANGUAGE_FIELDS = {'manuscript', 'response'}


def _yaml_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.suffix.lower() not in {'.yaml', '.yml'}:
        raise ValueError('only YAML project manifests are supported')
    return resolved


def _reject_unknown_fields(
    data: dict[str, Any], allowed: set[str], location: str
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        unknown_names = ', '.join(str(item) for item in unknown)
        raise ValueError(
            f'unknown {location} field(s): {unknown_names}'
        )


def _enum_name(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.strip().upper().replace(' ', '_').replace('-', '_')


def _normalize_nested_config(data: dict[str, Any]) -> dict[str, Any]:
    _reject_unknown_fields(data, _NESTED_TOP_LEVEL_FIELDS, 'top-level')

    project = data.get('project')
    languages = data.get('languages')
    if not isinstance(project, dict):
        raise ValueError('project must be a YAML mapping')
    if not isinstance(languages, dict):
        raise ValueError('languages must be a YAML mapping')
    _reject_unknown_fields(project, _PROJECT_FIELDS, 'project')
    _reject_unknown_fields(languages, _LANGUAGE_FIELDS, 'languages')

    highlight_policy = data.get('highlight_policy', {})
    if not isinstance(highlight_policy, dict):
        raise ValueError('highlight_policy must be a YAML mapping')
    normalized_highlights = {
        key: _enum_name(value) for key, value in highlight_policy.items()
    }

    return {
        'project_name': project.get('name'),
        'manuscript_id': project.get('manuscript_id'),
        'manuscript_title': project.get('manuscript_title', 'UNSPECIFIED'),
        'journal': project.get('journal'),
        'revision_round': project.get('revision_round'),
        'manuscript_language': languages.get('manuscript'),
        'response_language': languages.get('response'),
        'citation_style': data.get('citation_style'),
        'reviewer_count': data.get('reviewer_count'),
        'result_status': _enum_name(data.get('result_status')),
        'highlight_policy': normalized_highlights,
        'approval_gates': data.get('approval_gates', {}),
        'input_files': data.get('input_files', {}),
        'output_names': data.get('output_names'),
        'created_at': data.get('created_at'),
        'updated_at': data.get('updated_at'),
    }


def load_project_manifest(path: str | Path) -> ProjectManifest:
    '''Load one local YAML manifest without logging its contents.'''

    manifest_path = _yaml_path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f'project manifest not found: {manifest_path}')
    try:
        with manifest_path.open('r', encoding='utf-8') as stream:
            loaded = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ValueError(
            f'invalid YAML in project manifest: {manifest_path}'
        ) from exc
    except OSError as exc:
        raise OSError(f'unable to read project manifest: {manifest_path}') from exc

    if not isinstance(loaded, dict):
        raise ValueError('project manifest must contain a YAML mapping')

    if 'project' in loaded or 'languages' in loaded:
        manifest_data = _normalize_nested_config(loaded)
    else:
        _reject_unknown_fields(
            loaded, set(ProjectManifest.model_fields), 'top-level'
        )
        manifest_data = loaded

    try:
        return ProjectManifest.model_validate(manifest_data)
    except ValidationError as exc:
        raise ValueError(f'invalid project manifest: {manifest_path}: {exc}') from exc


def validate_default_project_config(path: str | Path) -> ProjectManifest:
    '''Validate a default project configuration and return its typed manifest.'''

    return load_project_manifest(path)


def save_project_manifest(manifest: ProjectManifest, path: str | Path) -> None:
    '''Serialize a validated manifest to YAML without network or logging.'''

    manifest_path = _yaml_path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode='json', exclude_none=True)
    try:
        with manifest_path.open('w', encoding='utf-8', newline='\n') as stream:
            yaml.safe_dump(
                payload,
                stream,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )
    except OSError as exc:
        raise OSError(f'unable to save project manifest: {manifest_path}') from exc
