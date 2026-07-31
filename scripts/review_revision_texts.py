'''Export or import explicit second-gate author decisions for revision text.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.services.gap_analysis_service import read_json  # noqa: E402
from scholarly_revision.workflows.revision_execution_workflow import (  # noqa: E402
    export_revision_text_decisions,
    import_completed_text_decisions,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Review exact revision texts.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--export-template', type=Path)
    parser.add_argument('--decision-file', type=Path)
    parser.add_argument('--list', action='store_true')
    arguments = parser.parse_args(argv)
    root = arguments.project_root.expanduser().resolve()
    if arguments.export_template and arguments.decision_file:
        parser.error('choose either --export-template or --decision-file')
    try:
        if arguments.export_template:
            path = export_revision_text_decisions(root, arguments.export_template)
            print(f'Text decision template: {path}')
        elif arguments.decision_file:
            result = import_completed_text_decisions(root, arguments.decision_file)
            print(f'Decisions recorded: {result.decision_count}')
            print(f'Decision audit: {result.decision_audit_path}')
            for decision, count in sorted(result.approval_counts.items()):
                print(f'{decision}: {count}')
        else:
            payload = read_json(root / 'working' / 'revision_drafts.json')
            for entry in payload.get('drafts', []):
                draft = entry['draft']
                print(
                    f"{draft['draft_id']} | {draft['approval_state']} | "
                    f"{draft['draft_status']} | {draft['action_id']}"
                )
    except Exception as exc:
        print(f'Revision-text review failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
