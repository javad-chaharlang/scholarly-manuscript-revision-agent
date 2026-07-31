'''Apply only explicitly exact-text-approved revisions to versioned DOCX copies.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.revision_execution_workflow import (  # noqa: E402
    apply_approved_revisions,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Safely apply approved revision text.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-manuscript', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = apply_approved_revisions(
            arguments.project_root, arguments.source_manuscript
        )
    except Exception as exc:
        print(f'Revision application failed: {exc}', file=sys.stderr)
        return 1
    print(f'Highlighted manuscript: {result.highlighted_path}')
    print(f'Clean manuscript: {result.clean_path}')
    print(f'Output version: {result.output_version}')
    print(f'Changes applied: {result.applied_change_count}')
    print(f'Changes blocked: {result.blocked_change_count}')
    print(f'Highlighted SHA-256: {result.highlighted_hash}')
    print(f'Clean SHA-256: {result.clean_hash}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
