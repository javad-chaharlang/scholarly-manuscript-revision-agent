'''Prepare or import explicit manual visual-QA decisions and rerun readiness.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from scholarly_revision.services.manual_visual_qa_service import (
    import_manual_visual_qa_decisions, prepare_manual_visual_qa_template,
)
from scholarly_revision.workflows.finalization_workflow import (
    run_final_consistency_check,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Prepare or import explicit manual visual-QA decisions.'
    )
    parser.add_argument('--project-root', required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--decisions', type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.prepare:
            path = prepare_manual_visual_qa_template(arguments.project_root)
            print(f'Manual visual-QA template: {path}')
            print('Approval inferred: False')
            return 0
        record = import_manual_visual_qa_decisions(
            arguments.project_root, arguments.decisions
        )
        result = run_final_consistency_check(arguments.project_root)
    except Exception as exc:
        print(f'Manual visual-QA workflow failed: {exc}', file=sys.stderr)
        return 1
    print(
        'Manual visual-QA decisions: '
        f'{len(record.decisions)}; all approved: {record.all_approved}'
    )
    print(f'Final readiness: {result.readiness}')
    print(f'Final release report: {result.final_release_report_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
