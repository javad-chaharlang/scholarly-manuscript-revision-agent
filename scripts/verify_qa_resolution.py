'''Verify Phase 6 resolution documentation and readiness.'''
from __future__ import annotations
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'src'
if str(SOURCE) not in sys.path:sys.path.insert(0,str(SOURCE))
from scholarly_revision.services.qa_report_service import verify_qa_resolutions

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description='Verify QA resolutions and readiness.')
    parser.add_argument('--project-root',required=True,type=Path);args=parser.parse_args(argv)
    try:result=verify_qa_resolutions(args.project_root)
    except Exception as exc:
        print(f'QA resolution verification failed: {exc}',file=sys.stderr);return 1
    print(f'Verification report: {args.project_root.resolve()/"audit"/"qa_resolution_verification.json"}')
    print(f'Blockers: {result["blocker_count"]}')
    print(f'Final readiness: {result["final_release_readiness"]}')
    return 0
if __name__=='__main__':raise SystemExit(main())
