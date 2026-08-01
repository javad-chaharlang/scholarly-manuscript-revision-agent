'''Confidential local workspace creation, input copying, and file hashing.'''

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE_DIRECTORIES = (
    'input', 'working', 'outputs', 'rendered', 'audit', 'config',
    'agent_runs', 'backups',
)


@dataclass(frozen=True, slots=True)
class ProjectWorkspace:
    root: Path
    slug: str
    input: Path
    working: Path
    outputs: Path
    rendered: Path
    audit: Path
    config: Path
    agent_runs: Path
    backups: Path


@dataclass(frozen=True, slots=True)
class InputFileRecord:
    role: str
    name: str
    stored_path: str
    size_bytes: int
    sha256: str
    copied_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def safe_project_slug(value: str, max_length: int = 64) -> str:
    '''Create a stable lowercase ASCII slug with no path components.'''

    if not isinstance(value, str) or not value.strip():
        raise ValueError('project name must be a non-empty string')
    normalized = unicodedata.normalize('NFKD', value)
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_value).strip('-')
    slug = re.sub(r'-{2,}', '-', slug)[:max_length].rstrip('-')
    if not slug:
        slug = 'revision-project'
    if slug in {'.', '..'}:
        raise ValueError('project name does not produce a safe slug')
    return slug


def _default_repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def create_project_workspace(
    workspace_root: str | Path,
    project_name: str,
    *,
    force: bool = False,
    repository_root: str | Path | None = None,
    allow_inside_repository: bool = False,
) -> ProjectWorkspace:
    '''Create the fixed local project tree without overwriting by default.'''

    root = Path(workspace_root).expanduser().resolve()
    repository = Path(repository_root or _default_repository_root()).resolve()
    if not allow_inside_repository and _is_within(root, repository):
        raise ValueError('workspace root must be outside the Git repository')

    slug = safe_project_slug(project_name)
    project_root = (root / slug).resolve()
    if project_root.parent != root:
        raise ValueError('project slug escaped the workspace root')
    root.mkdir(parents=True, exist_ok=True)
    if project_root.exists():
        if not force:
            raise FileExistsError(
                f'project already exists; use --force to replace it: {project_root}'
            )
        shutil.rmtree(project_root)

    project_root.mkdir()
    directories = {name: project_root / name for name in WORKSPACE_DIRECTORIES}
    for directory in directories.values():
        directory.mkdir()
    (directories['config'] / 'agent_settings.json').write_text(
        json.dumps({
            'codex_executable': None,
            'default_timeout_seconds': 300,
            'context_warning_characters': 40000,
            'global_concurrency': 1,
            'pilot_mode': True,
            'allow_semantic_tasks': True,
            'one_active_task_per_project': True,
            'abandoned_run_seconds': 60,
        }, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return ProjectWorkspace(root=project_root, slug=slug, **directories)


def sha256_file(path: str | Path) -> str:
    source = Path(path)
    digest = hashlib.sha256()
    try:
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
    except OSError as exc:
        raise OSError(f'unable to hash input file: {source}') from exc
    return digest.hexdigest()


def copy_input_file(
    source_path: str | Path,
    workspace: ProjectWorkspace,
    role: str,
) -> InputFileRecord:
    '''Copy one input without exposing its contents or changing the source.'''

    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'input file not found or unreadable: {source}')
    destination = workspace.input / source.name
    if destination.exists():
        raise FileExistsError(f'input file name collision: {source.name}')
    try:
        shutil.copy2(source, destination)
    except OSError as exc:
        raise OSError(f'unable to copy input file: {source.name}') from exc
    return InputFileRecord(
        role=role,
        name=source.name,
        stored_path=destination.relative_to(workspace.root).as_posix(),
        size_bytes=destination.stat().st_size,
        sha256=sha256_file(destination),
        copied_at=datetime.now(UTC).isoformat(),
    )
