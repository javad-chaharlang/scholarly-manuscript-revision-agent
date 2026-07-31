'''Prepare a blank, local Phase 4 gap-analysis package.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.workflows.gap_analysis_workflow import (  # noqa: E402
    prepare_gap_analysis,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Extract DOCX structure and prepare blank gap-analysis JSON.'
    )
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--manuscript-file', required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    try:
        result = prepare_gap_analysis(
            arguments.project_root, arguments.manuscript_file
        )
    except Exception as exc:
        print(f'Gap-analysis preparation failed: {exc}', file=sys.stderr)
        return 1
    print(f'Manuscript structure: {result.manuscript_structure_path}')
    print(f'Gap-analysis input: {result.gap_analysis_input_path}')
    print(f'Gap-analysis template: {result.gap_analysis_template_path}')
    print(f'Comments: {result.comment_count}')
    print(f'Structural elements: {result.structural_element_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
