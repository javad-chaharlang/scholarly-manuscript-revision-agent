import subprocess
import sys
from pathlib import Path

from phase7_helpers import (
    approved_manual_visual_qa_payload, make_ready_phase7_project,
)
from scholarly_revision.services.gap_analysis_service import write_json

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str):
    return subprocess.run(
        [sys.executable, *arguments], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )


def test_finalization_cli_success_and_failure_cases(tmp_path: Path) -> None:
    root = make_ready_phase7_project(tmp_path)
    response = root / 'outputs' / 'Response_to_Reviewers.docx'
    response.unlink()
    generated = run(
        'scripts/generate_response_letter.py', '--project-root', str(root),
        '--response-draft', str(root / 'working' / 'completed_response.json'),
    )
    assert generated.returncode == 0, generated.stderr
    verified = run(
        'scripts/verify_response_letter.py', '--project-root', str(root),
        '--response-letter', str(response),
    )
    assert verified.returncode == 0, verified.stderr
    decisions = root / 'working' / 'cli_visual_decisions.json'
    write_json(decisions, approved_manual_visual_qa_payload(root))
    inspected = run(
        'scripts/manual_visual_qa.py', '--project-root', str(root),
        '--decisions', str(decisions),
    )
    assert inspected.returncode == 0, inspected.stderr
    checked = run(
        'scripts/run_final_consistency_check.py', '--project-root', str(root)
    )
    assert checked.returncode == 0, checked.stderr
    released = run(
        'scripts/build_release_package.py', '--project-root', str(root),
        '--release-name', 'release_v001',
    )
    assert released.returncode == 0, released.stderr
    duplicate = run(
        'scripts/build_release_package.py', '--project-root', str(root),
        '--release-name', 'release_v001',
    )
    assert duplicate.returncode == 1
    missing = run(
        'scripts/generate_response_letter.py', '--project-root', str(root / 'missing'),
        '--response-draft', str(root / 'missing.json'),
    )
    assert missing.returncode == 1
