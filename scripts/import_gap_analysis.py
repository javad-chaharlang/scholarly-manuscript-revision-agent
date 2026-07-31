'''Strictly import a completed local gap analysis and create a draft plan.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.gap_analysis_workflow import import_and_plan  # noqa: E402


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate completed gap analysis and generate an unapproved plan.'
    )
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--analysis-file', required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    try:
        result = import_and_plan(arguments.project_root, arguments.analysis_file)
    except Exception as exc:
        print(f'Gap-analysis import failed: {exc}', file=sys.stderr)
        return 1
    print(f'Revision plan: {result.revision_plan_path}')
    print(f'Gap-analysis report: {result.gap_analysis_report_path}')
    print(f'Workbook: {result.workbook_path}')
    print(f'Actions: {result.action_count}')
    print(f'Approval gate: {result.approval_gate_status}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
