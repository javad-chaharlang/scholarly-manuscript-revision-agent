from hashlib import sha256
from pathlib import Path

import pytest

from scholarly_revision.services.project_workspace import (
    WORKSPACE_DIRECTORIES,
    copy_input_file,
    create_project_workspace,
    safe_project_slug,
)


def test_safe_project_slug_generation() -> None:
    assert safe_project_slug('  Anonymous Revision: Round 1  ') == 'anonymous-revision-round-1'
    assert safe_project_slug('../../Unsafe Project') == 'unsafe-project'


def test_local_workspace_creation_copy_and_sha256(tmp_path: Path) -> None:
    repository = tmp_path / 'repository'
    repository.mkdir()
    workspace_root = tmp_path / 'private-workspaces'
    workspace = create_project_workspace(
        workspace_root,
        'Synthetic Project',
        repository_root=repository,
    )
    assert all((workspace.root / name).is_dir() for name in WORKSPACE_DIRECTORIES)
    source = tmp_path / 'anonymous-input.docx'
    source.write_bytes(b'anonymous synthetic bytes')
    record = copy_input_file(source, workspace, 'reviewer_comments')
    copied = workspace.root / record.stored_path
    assert copied.read_bytes() == source.read_bytes()
    assert record.sha256 == sha256(source.read_bytes()).hexdigest()
    assert record.size_bytes == source.stat().st_size


def test_overwrite_refusal_and_explicit_force(tmp_path: Path) -> None:
    repository = tmp_path / 'repository'
    repository.mkdir()
    root = tmp_path / 'workspaces'
    first = create_project_workspace(root, 'Project', repository_root=repository)
    marker = first.working / 'marker.txt'
    marker.write_text('synthetic', encoding='utf-8')
    with pytest.raises(FileExistsError, match='--force'):
        create_project_workspace(root, 'Project', repository_root=repository)
    replaced = create_project_workspace(
        root, 'Project', force=True, repository_root=repository
    )
    assert not (replaced.working / 'marker.txt').exists()


def test_workspace_inside_repository_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / 'repository'
    repository.mkdir()
    with pytest.raises(ValueError, match='outside the Git repository'):
        create_project_workspace(
            repository / 'private', 'Project', repository_root=repository
        )
