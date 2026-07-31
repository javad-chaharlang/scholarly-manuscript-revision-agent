'''Export stable JSON Schemas for the Phase 2 domain models.'''

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.models import (  # noqa: E402
    EvidenceRecord,
    ExperimentalResultRecord,
    ProjectManifest,
    QAFinding,
    ReferenceRecord,
    ResponseLetterEntry,
    ReviewerComment,
    RevisionAction,
    RevisionDraft,
    TraceabilityRecord,
)


ModelType: TypeAlias = type[BaseModel]
SCHEMA_MODELS: tuple[tuple[str, ModelType], ...] = (
    ('project-manifest.schema.json', ProjectManifest),
    ('reviewer-comment.schema.json', ReviewerComment),
    ('revision-action.schema.json', RevisionAction),
    ('revision-draft.schema.json', RevisionDraft),
    ('evidence-record.schema.json', EvidenceRecord),
    ('experimental-result-record.schema.json', ExperimentalResultRecord),
    ('reference-record.schema.json', ReferenceRecord),
    ('traceability-record.schema.json', TraceabilityRecord),
    ('response-letter-entry.schema.json', ResponseLetterEntry),
    ('qa-finding.schema.json', QAFinding),
)


def export_schemas(output_directory: str | Path | None = None) -> list[Path]:
    destination = (
        Path(output_directory)
        if output_directory is not None
        else REPOSITORY_ROOT / 'schemas'
    )
    destination.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for file_name, model in SCHEMA_MODELS:
        target = destination / file_name
        schema = model.model_json_schema()
        with target.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(schema, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write('\n')
        written.append(target)
    return written


def main() -> int:
    try:
        export_schemas()
    except Exception as exc:
        print(f'schema export failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
