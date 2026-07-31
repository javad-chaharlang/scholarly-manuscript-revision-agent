import subprocess,sys
from pathlib import Path
from phase6_helpers import CONFIG,REFERENCES,RESULTS,make_qa_project
ROOT=Path(__file__).resolve().parents[1]

def test_cli_success_blocker_exit_and_failure(tmp_path:Path) -> None:
    project,highlighted,clean=make_qa_project(tmp_path)
    base=[sys.executable,'scripts/run_scientific_qa.py','--project-root',str(project),
        '--highlighted-manuscript',str(highlighted),'--clean-manuscript',str(clean),
        '--results-registry',str(RESULTS),'--reference-registry',str(REFERENCES),'--config',str(CONFIG)]
    completed=subprocess.run(base,cwd=ROOT,capture_output=True,text=True,check=False)
    assert completed.returncode==0,completed.stderr
    assert 'Final readiness: BLOCKED' in completed.stdout
    blocked=subprocess.run([*base,'--fail-on-blockers'],cwd=ROOT,capture_output=True,text=True,check=False)
    assert blocked.returncode==2
    failed=subprocess.run([sys.executable,'scripts/run_scientific_qa.py','--project-root',str(project),
        '--highlighted-manuscript',str(project/'missing.docx'),'--clean-manuscript',str(clean)],
        cwd=ROOT,capture_output=True,text=True,check=False)
    assert failed.returncode==1
