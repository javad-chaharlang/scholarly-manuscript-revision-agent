import subprocess
import sys
from pathlib import Path

from phase5_helpers import MANUSCRIPT, make_phase5_project, setup_approved_project

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str):
    return subprocess.run(
        [sys.executable, *arguments], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )


def test_prepare_failure_apply_and_verify_cli(tmp_path: Path) -> None:
    project = make_phase5_project(tmp_path / 'prepare', action_count=1)
    prepared = run(
        'scripts/prepare_revision_drafts.py', '--project-root', str(project)
    )
    assert prepared.returncode == 0, prepared.stderr
    assert 'Drafts prepared: 1' in prepared.stdout

    failed = run(
        'scripts/apply_approved_revisions.py', '--project-root', str(project),
        '--source-manuscript', str(MANUSCRIPT),
    )
    assert failed.returncode != 0
    assert 'Revision application failed:' in failed.stderr

    approved = setup_approved_project(tmp_path / 'approved')
    applied = run(
        'scripts/apply_approved_revisions.py', '--project-root', str(approved),
        '--source-manuscript', str(MANUSCRIPT),
    )
    assert applied.returncode == 0, applied.stderr
    assert 'Changes applied: 6' in applied.stdout
    verified = run(
        'scripts/verify_revision_outputs.py', '--project-root', str(approved),
        '--source-manuscript', str(MANUSCRIPT),
    )
    assert verified.returncode == 0, verified.stderr
    assert 'Verification passed: True' in verified.stdout
