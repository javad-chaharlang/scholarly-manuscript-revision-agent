'''Build one immutable, allowlisted local submission package.'''
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from scholarly_revision.workflows.finalization_workflow import build_submission_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build an immutable release package.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--release-name', required=True)
    arguments = parser.parse_args(argv)
    try:
        result = build_submission_package(
            arguments.project_root, arguments.release_name
        )
    except Exception as exc:
        print(f'Release package failed: {exc}', file=sys.stderr)
        return 1
    print(f'Release package: {result.package_path}')
    print(f'Release manifest: {result.manifest_path}')
    print(f'Artifacts: {len(result.manifest.artifacts)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
