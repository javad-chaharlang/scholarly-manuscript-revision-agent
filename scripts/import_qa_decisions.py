'''Import explicit Phase 6 QA decisions.'''
from __future__ import annotations
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'src'
if str(SOURCE) not in sys.path:sys.path.insert(0,str(SOURCE))
from scholarly_revision.services.qa_report_service import apply_qa_decisions

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description='Import explicit QA decisions.')
    parser.add_argument('--project-root',required=True,type=Path)
    parser.add_argument('--decision-file',required=True,type=Path)
    args=parser.parse_args(argv)
    try:report=apply_qa_decisions(args.project_root,args.decision_file)
    except Exception as exc:
        print(f'QA decision import failed: {exc}',file=sys.stderr);return 1
    print(f'Decisions imported from: {args.decision_file}')
    print(f'Blockers: {report.blocker_count}')
    print(f'Final readiness: {report.final_release_readiness.value}')
    return 0
if __name__=='__main__':raise SystemExit(main())
