import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / 'fixtures' / 'synthetic_reviewer_comments.docx'


def command(workspace_root: Path) -> list[str]:
    return [
        sys.executable,
        'scripts/create_revision_project.py',
        '--workspace-root',
        str(workspace_root),
        '--project-name',
        'CLI Synthetic Project',
        '--manuscript-id',
        'SYNTHETIC-ID',
        '--reviewer-file',
        str(FIXTURE),
        '--reviewer-count',
        '2',
    ]


def test_cli_success_prints_only_safe_summary(tmp_path: Path) -> None:
    completed = subprocess.run(
        command(tmp_path / 'workspaces'),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'Extracted comments: 7' in completed.stdout
    assert 'Manual review required: 1' in completed.stdout
    assert 'Please clarify' not in completed.stdout
    project = tmp_path / 'workspaces' / 'cli-synthetic-project'
    assert (project / 'outputs' / 'Revision_Master.xlsx').is_file()


def test_cli_refuses_existing_project_without_force(tmp_path: Path) -> None:
    args = command(tmp_path / 'workspaces')
    first = subprocess.run(
        args, cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False
    )
    second = subprocess.run(
        args, cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False
    )
    assert first.returncode == 0
    assert second.returncode != 0
    assert 'use --force' in second.stderr
