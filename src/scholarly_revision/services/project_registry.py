'''Workspace-scoped, local project registry stored outside the repository.'''

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from scholarly_revision.models.project_state import (
    ProjectRegistryEntry, ProjectRegistryFile, ProjectState,
)
from scholarly_revision.services.config_loader import load_project_manifest


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class ProjectRegistry:
    '''Discover and resume projects without copying confidential project data.'''

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        if _inside(self.workspace_root, _repository_root()):
            raise ValueError('registry workspace root must be outside the Git repository')
        self.registry_directory = self.workspace_root / '.scholarly_revision'
        self.path = self.registry_directory / 'registry.json'

    def _load_file(self) -> ProjectRegistryFile:
        if not self.path.is_file():
            return ProjectRegistryFile()
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'invalid local project registry: {self.path}') from exc
        return ProjectRegistryFile.model_validate(payload)

    def _save_file(self, registry: ProjectRegistryFile) -> None:
        self.registry_directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix='registry-', suffix='.json.tmp', dir=self.registry_directory
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                json.dump(
                    registry.model_dump(mode='json'), stream,
                    indent=2, sort_keys=True, ensure_ascii=False,
                )
                stream.write('\n')
            os.replace(temporary, self.path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def list_projects(self, *, existing_only: bool = True) -> list[ProjectRegistryEntry]:
        projects = self._load_file().projects
        if existing_only:
            projects = [item for item in projects if Path(item.project_root).is_dir()]
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def get(self, project_id: str) -> ProjectRegistryEntry:
        for entry in self._load_file().projects:
            if entry.project_id == project_id:
                return entry
        raise KeyError(f'project is not registered: {project_id}')

    def register(
        self, project_root: str | Path, state: ProjectState,
        *, project_id: str | None = None,
    ) -> ProjectRegistryEntry:
        root = Path(project_root).expanduser().resolve()
        if not _inside(root, self.workspace_root):
            raise ValueError('project root must be inside the selected workspace root')
        manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
        now = datetime.now(UTC)
        identifier = project_id or root.name
        entry = ProjectRegistryEntry(
            project_id=identifier,
            project_name=manifest.project_name,
            manuscript_id=manifest.manuscript_id,
            project_root=str(root),
            state=state,
            created_at=manifest.created_at or now,
            updated_at=now,
        )
        registry = self._load_file()
        retained = [
            item for item in registry.projects
            if item.project_id != identifier
            and Path(item.project_root).resolve() != root
        ]
        self._save_file(ProjectRegistryFile(projects=[*retained, entry]))
        return entry

    def update_state(self, project_id: str, state: ProjectState) -> ProjectRegistryEntry:
        registry = self._load_file()
        found: ProjectRegistryEntry | None = None
        updated: list[ProjectRegistryEntry] = []
        for entry in registry.projects:
            if entry.project_id == project_id:
                found = entry.model_copy(update={
                    'state': state, 'updated_at': datetime.now(UTC),
                })
                updated.append(found)
            else:
                updated.append(entry)
        if found is None:
            raise KeyError(f'project is not registered: {project_id}')
        self._save_file(ProjectRegistryFile(projects=updated))
        return found
