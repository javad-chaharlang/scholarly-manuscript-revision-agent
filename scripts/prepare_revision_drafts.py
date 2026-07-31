'''Prepare blank exact-text revision drafts for approved Phase 4 actions.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.revision_execution_workflow import (  # noqa: E402
    prepare_revision_drafts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prepare deterministic blank revision drafts.')
    parser.add_argument('--project-root', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = prepare_revision_drafts(arguments.project_root)
    except Exception as exc:
        print(f'Revision-draft preparation failed: {exc}', file=sys.stderr)
        return 1
    print(f'Drafting input: {result.drafting_input_path}')
    print(f'Draft template: {result.draft_template_path}')
    print(f'Drafting report: {result.drafting_report_path}')
    print(f'Drafts prepared: {result.draft_count}')
    print(f'Actions blocked: {result.blocked_action_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
