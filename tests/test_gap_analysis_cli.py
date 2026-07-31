import json
import subprocess
import sys
from pathlib import Path

from scholarly_revision.workflows.intake_workflow import IntakeRequest, run_intake_workflow

ROOT = Path(__file__).resolve().parents[1]
REVIEWERS = Path(__file__).parent / 'fixtures' / 'synthetic_reviewer_comments.docx'
MANUSCRIPT = Path(__file__).parent / 'fixtures' / 'synthetic_manuscript.docx'


def test_prepare_import_and_list_cli(tmp_path: Path) -> None:
    project = run_intake_workflow(IntakeRequest(workspace_root=tmp_path / 'workspaces',
        project_name='CLI Phase Four', manuscript_id='SYNTHETIC',
        reviewer_file=REVIEWERS, manuscript_file=MANUSCRIPT)).workspace.root
    prepared = subprocess.run([sys.executable, 'scripts/prepare_gap_analysis.py',
        '--project-root', str(project), '--manuscript-file', str(MANUSCRIPT)],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert prepared.returncode == 0, prepared.stderr
    failed_file = project / 'working' / 'bad.json'
    failed_file.write_text(json.dumps({'assessments': []}), encoding='utf-8')
    failed = subprocess.run([sys.executable, 'scripts/import_gap_analysis.py',
        '--project-root', str(project), '--analysis-file', str(failed_file)],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert failed.returncode != 0
    payload = json.loads((project / 'working' / 'gap_analysis_template.json').read_text(encoding='utf-8'))
    for item in payload['assessments']:
        item.update({'coverage_status': 'NOT_APPLICABLE',
            'interpretation': 'No action required.', 'author_decision_required': True,
            'confidence': 1.0, 'manual_review_required': False})
    completed = project / 'working' / 'completed.json'
    completed.write_text(json.dumps(payload), encoding='utf-8')
    imported = subprocess.run([sys.executable, 'scripts/import_gap_analysis.py',
        '--project-root', str(project), '--analysis-file', str(completed)],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert imported.returncode == 0, imported.stderr
    listed = subprocess.run([sys.executable, 'scripts/review_revision_plan.py',
        '--project-root', str(project), '--list'], cwd=ROOT,
        capture_output=True, text=True, check=False)
    assert listed.returncode == 0
    assert 'Approval gate: NOT_READY' in listed.stdout
