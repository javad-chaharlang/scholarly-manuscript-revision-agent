'''Run deterministic Phase 6 scientific QA and print only safe summaries.'''
from __future__ import annotations
import argparse,sys
from pathlib import Path
REPOSITORY_ROOT=Path(__file__).resolve().parents[1];SOURCE_ROOT=REPOSITORY_ROOT/'src'
if str(SOURCE_ROOT) not in sys.path:sys.path.insert(0,str(SOURCE_ROOT))
from scholarly_revision.workflows.scientific_qa_workflow import run_scientific_qa_workflow

def build_argument_parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description='Run deterministic local scientific QA.')
    parser.add_argument('--project-root',required=True,type=Path)
    parser.add_argument('--highlighted-manuscript',required=True,type=Path)
    parser.add_argument('--clean-manuscript',required=True,type=Path)
    parser.add_argument('--results-registry',type=Path)
    parser.add_argument('--reference-registry',type=Path)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--fail-on-blockers',action='store_true')
    return parser

def main(argv:list[str]|None=None)->int:
    arguments=build_argument_parser().parse_args(argv)
    try:
        result=run_scientific_qa_workflow(project_root=arguments.project_root,
            highlighted_manuscript=arguments.highlighted_manuscript,
            clean_manuscript=arguments.clean_manuscript,
            results_registry=arguments.results_registry,
            reference_registry=arguments.reference_registry,config_path=arguments.config)
    except Exception as exc:
        print(f'Scientific QA failed: {exc}',file=sys.stderr);return 1
    print(f'QA report: {result.report_paths["json"]}')
    print(f'QA workbook: {result.report_paths["xlsx"]}')
    print(f'Revision workbook: {result.workbook_path}')
    print(f'Total issues: {result.report.total_issues}')
    print(f'Blockers: {result.report.blocker_count}')
    print(f'Final readiness: {result.report.final_release_readiness.value}')
    if arguments.fail_on_blockers and result.report.blocker_count:return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
