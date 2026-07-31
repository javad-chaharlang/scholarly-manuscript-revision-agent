import json
import subprocess
import sys
from pathlib import Path

from scripts.export_schemas import SCHEMA_MODELS, export_schemas


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_export_schemas_to_requested_directory(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    assert len(written) == len(SCHEMA_MODELS)
    assert {path.name for path in written} == {
        file_name for file_name, _ in SCHEMA_MODELS
    }
    for schema_path in written:
        schema = json.loads(schema_path.read_text(encoding='utf-8'))
        assert schema['title']
        assert schema['type'] == 'object'


def test_schema_export_script_succeeds_without_network() -> None:
    completed = subprocess.run(
        [sys.executable, 'scripts/export_schemas.py'],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (REPOSITORY_ROOT / 'schemas' / 'project-manifest.schema.json').is_file()
