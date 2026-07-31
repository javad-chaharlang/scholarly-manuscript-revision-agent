'''Verify the complete Phase 5 revision output package.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.revision_execution_workflow import (  # noqa: E402
    verify_revision_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Verify highlighted and clean revision outputs.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-manuscript', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = verify_revision_outputs(
            arguments.project_root, arguments.source_manuscript
        )
    except Exception as exc:
        print(f'Revision-output verification failed: {exc}', file=sys.stderr)
        return 1
    print(f"Verification passed: {report['passed']}")
    print(f"Output version: {report['output_version']}")
    print(f"Applied changes: {report['applied_change_count']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
