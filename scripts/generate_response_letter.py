'''Generate a local response DOCX from a strictly completed response draft.'''
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from scholarly_revision.workflows.finalization_workflow import generate_response_letter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate response-to-reviewers files.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--response-draft', required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = generate_response_letter(
            arguments.project_root, arguments.response_draft
        )
    except Exception as exc:
        print(f'Response generation failed: {exc}', file=sys.stderr)
        return 1
    print(f'Response letter: {result.response_letter_path}')
    print(f'Response package: {result.response_package_path}')
    print(f'Generation report: {result.generation_report_path}')
    print(f'Response entries: {len(result.package.entries)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
