'''Create a confidential local Phase 3 revision project.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.intake_workflow import (  # noqa: E402
    IntakeRequest,
    run_intake_workflow,
)


def _non_empty(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError('value must not be empty')
    return value.strip()


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be an integer') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError('must be positive')
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Create a deterministic local manuscript revision project.'
    )
    parser.add_argument('--workspace-root', required=True, type=Path)
    parser.add_argument('--project-name', required=True, type=_non_empty)
    parser.add_argument('--manuscript-id', required=True, type=_non_empty)
    parser.add_argument('--reviewer-file', required=True, type=Path)
    parser.add_argument('--manuscript-file', type=Path)
    parser.add_argument('--journal', type=_non_empty)
    parser.add_argument('--reviewer-count', type=_positive_integer)
    parser.add_argument('--force', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    try:
        result = run_intake_workflow(
            IntakeRequest(
                workspace_root=arguments.workspace_root,
                project_name=arguments.project_name,
                manuscript_id=arguments.manuscript_id,
                reviewer_file=arguments.reviewer_file,
                manuscript_file=arguments.manuscript_file,
                journal=arguments.journal,
                reviewer_count=arguments.reviewer_count,
                force=arguments.force,
            )
        )
    except Exception as exc:
        print(f'Project creation failed: {exc}', file=sys.stderr)
        return 1

    print(f'Project workspace: {result.workspace.root}')
    print(f'Extracted comments: {len(result.extracted_comment_ids)}')
    print(f'Manual review required: {result.manual_review_count}')
    print(f'Workbook: {result.workbook_path}')
    for warning in result.warnings:
        print(f'Warning: {warning}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
