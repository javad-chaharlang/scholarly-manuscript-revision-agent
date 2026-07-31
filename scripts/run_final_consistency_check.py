'''Run the Phase 7 cross-document consistency and release-readiness gate.'''
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from scholarly_revision.workflows.finalization_workflow import run_final_consistency_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run final consistency checks.')
    parser.add_argument('--project-root', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = run_final_consistency_check(arguments.project_root)
    except Exception as exc:
        print(f'Final consistency check failed: {exc}', file=sys.stderr)
        return 1
    print(f'Consistency JSON: {result.consistency_json_path}')
    print(f'Consistency CSV: {result.consistency_csv_path}')
    print(f'Final checklist: {result.checklist_path}')
    print(f'Consistency findings: {len(result.consistency_report.findings)}')
    print(f'Final readiness: {result.readiness}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
