'''Immutable manuscript version allocation and manifest recording.'''

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.revision_draft import DocumentVersionRecord
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.project_workspace import sha256_file


_VERSION_FILE = re.compile(r'^manuscript_v(?P<number>\d{3,})_(?P<role>source|highlighted|clean)\.docx$')


@dataclass(frozen=True, slots=True)
class VersionAllocation:
    source_version: str
    output_version: str
    source_copy_path: Path
    highlighted_path: Path
    clean_path: Path
    backup_path: Path
    source_hash: str
    parent_version: str


def _manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': 1, 'versions': []}
    payload = read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get('versions'), list):
        raise ValueError('document_version_manifest.json is malformed')
    return payload


def next_version_number(versions_directory: str | Path) -> int:
    directory = Path(versions_directory)
    numbers = [
        int(match.group('number'))
        for path in directory.glob('manuscript_v*_*.docx')
        if (match := _VERSION_FILE.fullmatch(path.name))
    ]
    return max(numbers, default=0) + 1


def _next_allocated_version(directory: Path, manifest: dict[str, Any]) -> int:
    file_next = next_version_number(directory)
    reserved = [
        int(str(value).removeprefix('v'))
        for value in manifest.get('reserved_output_versions', [])
        if re.fullmatch(r'v\d{3,}', str(value))
    ]
    recorded = [
        int(str(item.get('version')).removeprefix('v'))
        for item in manifest.get('versions', [])
        if re.fullmatch(r'v\d{3,}', str(item.get('version')))
    ]
    return max([file_next - 1, *reserved, *recorded], default=0) + 1

def allocate_document_versions(
    project_root: str | Path,
    source_manuscript: str | Path,
) -> VersionAllocation:
    root = Path(project_root).expanduser().resolve()
    source = Path(source_manuscript).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f'source manuscript not found: {source}')
    versions = root / 'outputs' / 'versions'
    backups = root / 'audit' / 'backups'
    versions.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'audit' / 'document_version_manifest.json'
    manifest = _manifest(manifest_path)
    source_hash = sha256_file(source)

    prior_source = next(
        (
            item for item in manifest['versions']
            if item.get('role') == 'source' and item.get('source_hash') == source_hash
        ),
        None,
    )
    now = datetime.now(UTC)
    if prior_source:
        source_version = str(prior_source['version'])
        source_copy = versions / str(prior_source['file_name'])
        if not source_copy.is_file() or sha256_file(source_copy) != source_hash:
            raise ValueError('recorded immutable source version is missing or changed')
    else:
        source_number = _next_allocated_version(versions, manifest)
        source_version = f'v{source_number:03d}'
        source_copy = versions / f'manuscript_{source_version}_source.docx'
        if source_copy.exists():
            raise FileExistsError(f'version file already exists: {source_copy}')
        shutil.copy2(source, source_copy)
        source_record = DocumentVersionRecord(
            version=source_version,
            role='source',
            file_name=source_copy.name,
            source_hash=source_hash,
            output_hash=sha256_file(source_copy),
            parent_version=None,
            creation_timestamp=now,
            verification_result='SOURCE_HASH_VERIFIED',
        )
        manifest['versions'].append(source_record.model_dump(mode='json'))
        write_json(manifest_path, manifest)

    output_number = _next_allocated_version(versions, manifest)
    output_version = f'v{output_number:03d}'
    highlighted = versions / f'manuscript_{output_version}_highlighted.docx'
    clean = versions / f'manuscript_{output_version}_clean.docx'
    if highlighted.exists() or clean.exists():
        raise FileExistsError(f'output version {output_version} already exists')

    reservations = manifest.setdefault('reserved_output_versions', [])
    if output_version in reservations:
        raise FileExistsError(f'output version {output_version} is already reserved')
    reservations.append(output_version)
    write_json(manifest_path, manifest)
    backup_name = (
        f'application_backup_{now.strftime("%Y%m%dT%H%M%S%fZ")}_{source_hash[:12]}.docx'
    )
    backup = backups / backup_name
    shutil.copy2(source, backup)
    if sha256_file(backup) != source_hash:
        raise ValueError('application backup hash verification failed')
    return VersionAllocation(
        source_version=source_version,
        output_version=output_version,
        source_copy_path=source_copy,
        highlighted_path=highlighted,
        clean_path=clean,
        backup_path=backup,
        source_hash=source_hash,
        parent_version=source_version,
    )


def finalize_document_versions(
    project_root: str | Path,
    allocation: VersionAllocation,
    *,
    applied_change_ids: list[str],
    verification_result: str,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    manifest_path = root / 'audit' / 'document_version_manifest.json'
    manifest = _manifest(manifest_path)
    now = datetime.now(UTC)
    for role, path in (
        ('highlighted', allocation.highlighted_path),
        ('clean', allocation.clean_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f'versioned {role} manuscript is missing: {path}')
        record = DocumentVersionRecord(
            version=allocation.output_version,
            role=role,
            file_name=path.name,
            source_hash=allocation.source_hash,
            output_hash=sha256_file(path),
            parent_version=allocation.parent_version,
            creation_timestamp=now,
            applied_change_ids=applied_change_ids,
            verification_result=verification_result,
        )
        manifest['versions'].append(record.model_dump(mode='json'))
    manifest['latest_output_version'] = allocation.output_version
    write_json(manifest_path, manifest)
    return manifest
