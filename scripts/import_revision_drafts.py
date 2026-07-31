'''Strictly import completed local exact-text revision drafts.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.revision_execution_workflow import (  # noqa: E402
    import_completed_revision_drafts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate and import completed revision drafts.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--draft-file', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = import_completed_revision_drafts(
            arguments.project_root, arguments.draft_file
        )
    except Exception as exc:
        print(f'Revision-draft import failed: {exc}', file=sys.stderr)
        return 1
    print(f'Revision drafts: {result.revision_drafts_path}')
    print(f'Import report: {result.import_report_path}')
    print(f'Drafts imported: {result.draft_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
