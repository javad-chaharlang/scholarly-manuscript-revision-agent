'''Start the fully local Streamlit application.'''

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'src' / 'scholarly_revision' / 'ui' / 'app.py'


def build_command(*, port: int, headless: bool) -> list[str]:
    return [
        sys.executable, '-m', 'streamlit', 'run', str(APP),
        '--server.address', 'localhost',
        '--server.port', str(port),
        '--server.headless', 'true' if headless else 'false',
        '--browser.gatherUsageStats', 'false',
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run the local manuscript revision UI.')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--headless', action='store_true')
    arguments = parser.parse_args(argv)
    url = f'http://localhost:{arguments.port}'
    print(f'Local URL: {url}', flush=True)
    return subprocess.call(build_command(port=arguments.port, headless=arguments.headless))


if __name__ == '__main__':
    raise SystemExit(main())
