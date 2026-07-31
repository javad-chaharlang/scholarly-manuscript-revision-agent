from pathlib import Path

import pytest

from scholarly_revision.models.enums import HighlightColor, ResultStatus
from scholarly_revision.services.config_loader import (
    load_project_manifest,
    save_project_manifest,
    validate_default_project_config,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_load_default_project_config() -> None:
    manifest = validate_default_project_config(
        REPOSITORY_ROOT / 'config' / 'default-project.yaml'
    )
    assert manifest.project_name == 'untitled-manuscript-revision'
    assert manifest.manuscript_title == 'UNSPECIFIED'
    assert manifest.result_status is ResultStatus.DRAFT
    assert manifest.highlight_policy.reviewer_1 is HighlightColor.YELLOW
    assert (
        manifest.highlight_policy.reviewer_2 is HighlightColor.BRIGHT_GREEN
    )
    assert (
        manifest.highlight_policy.shared_and_general is HighlightColor.VIOLET
    )


def test_invalid_yaml_has_clear_error(tmp_path: Path) -> None:
    invalid = tmp_path / 'invalid.yaml'
    invalid.write_text('project: [unterminated', encoding='utf-8')
    with pytest.raises(ValueError, match='invalid YAML'):
        load_project_manifest(invalid)


def test_missing_file_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match='not found'):
        load_project_manifest(tmp_path / 'missing.yaml')


def test_only_yaml_is_supported(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='only YAML'):
        load_project_manifest(tmp_path / 'manifest.json')


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / 'unknown.yaml'
    invalid.write_text(
        'project:\n'
        '  name: anonymous\n'
        '  manuscript_id: SYNTHETIC\n'
        '  journal: Example\n'
        '  revision_round: 1\n'
        'languages:\n'
        '  manuscript: English\n'
        '  response: English\n'
        'unexpected: true\n',
        encoding='utf-8',
    )
    with pytest.raises(ValueError, match='unknown top-level'):
        load_project_manifest(invalid)


def test_save_and_reload_manifest(tmp_path: Path) -> None:
    manifest = load_project_manifest(
        REPOSITORY_ROOT / 'config' / 'default-project.yaml'
    )
    saved = tmp_path / 'saved.yaml'
    save_project_manifest(manifest, saved)
    assert load_project_manifest(saved) == manifest
