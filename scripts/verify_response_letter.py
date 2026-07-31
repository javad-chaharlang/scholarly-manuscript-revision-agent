'''Verify a generated response letter against every local source record.'''
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from scholarly_revision.workflows.finalization_workflow import verify_response_letter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verify a response-to-reviewers DOCX.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--response-letter', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = verify_response_letter(
            arguments.project_root, arguments.response_letter
        )
    except Exception as exc:
        print(f'Response verification failed: {exc}', file=sys.stderr)
        return 1
    print(f'Verification report: {result.report_path}')
    print(f'Verified responses: {result.verified_count}')
    print(f'Blocked responses: {result.blocked_count}')
    print(f'Verification passed: {result.passed}')
    return 0 if result.passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
