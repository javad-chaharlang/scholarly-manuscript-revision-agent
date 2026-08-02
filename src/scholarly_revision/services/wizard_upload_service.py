'''Serializable, filesystem-backed upload drafts for the New Project wizard.'''

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from uuid import uuid4

from scholarly_revision.ui.state import safe_upload_name


REVIEWER_ROLE = 'reviewer_file'
MANUSCRIPT_ROLE = 'manuscript_file'
REQUIRED_ROLES = (REVIEWER_ROLE, MANUSCRIPT_ROLE)
DOCX_MEMBERS = ('[Content_Types].xml', 'word/document.xml')
MANIFEST_NAME = 'wizard_draft.json'
DEFAULT_DRAFT_ROOT_NAME = 'scholarly-revision-wizard'


class WizardUploadError(ValueError):
    '''A user-correctable upload validation failure.'''


@dataclass(frozen=True, slots=True)
class UploadRecord:
    role: str
    original_name: str
    safe_name: str
    extension: str
    mime_type: str
    size_bytes: int
    sha256: str
    temporary_path: str
    valid_docx: bool
    non_empty: bool
    validation_message: str
    uploaded_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> 'UploadRecord':
        return cls(**{name: value[name] for name in cls.__dataclass_fields__})


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def default_draft_root() -> Path:
    return (Path(tempfile.gettempdir()) / DEFAULT_DRAFT_ROOT_NAME).resolve()


def create_draft_directory(
    *, draft_root: str | Path | None = None, draft_id: str | None = None,
) -> tuple[str, Path]:
    base = Path(draft_root or default_draft_root()).expanduser().resolve()
    if _is_within(base, repository_root()):
        raise ValueError('wizard upload storage must be outside the Git repository')
    identifier = draft_id or uuid4().hex
    if not identifier or any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for character in identifier):
        raise ValueError('wizard draft ID contains unsafe characters')
    directory = (base / identifier).resolve()
    if directory.parent != base:
        raise ValueError('wizard draft directory escaped its storage root')
    (directory / 'uploads').mkdir(parents=True, exist_ok=True)
    return identifier, directory


def validate_docx_bytes(payload: bytes) -> tuple[bool, str]:
    if not payload:
        raise WizardUploadError('Return to Step 3 and upload a non-empty valid DOCX file.')
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
            missing = [name for name in DOCX_MEMBERS if name not in names]
            if missing:
                raise WizardUploadError(
                    'The selected file is not a valid DOCX: required document parts are missing.'
                )
            for name in DOCX_MEMBERS:
                if not archive.read(name):
                    raise WizardUploadError(
                        'The selected file is not a valid DOCX: a required document part is empty.'
                    )
            corrupt = archive.testzip()
            if corrupt is not None:
                raise WizardUploadError('The selected DOCX contains a damaged ZIP entry.')
    except (zipfile.BadZipFile, OSError) as exc:
        raise WizardUploadError('The selected file is not a structurally valid DOCX.') from exc
    return True, 'DOCX structure is valid.'


def _validate_payload(payload: bytes, extension: str) -> tuple[bool, str]:
    if not payload:
        raise WizardUploadError('The selected file is empty. Select a non-empty file.')
    if extension == '.docx':
        return validate_docx_bytes(payload)
    if extension == '.json':
        try:
            value = json.loads(payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WizardUploadError('The selected file is not readable JSON.') from exc
        if not isinstance(value, (dict, list)):
            raise WizardUploadError('The selected JSON must contain an object or list.')
        return False, 'JSON structure is valid.'
    raise WizardUploadError(f'Unsupported upload type: {extension or "unknown"}.')


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        finally:
            raise

def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def persist_upload(
    *, payload: bytes, original_name: str, mime_type: str | None, role: str,
    draft_directory: str | Path, existing_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    '''Validate and atomically save one upload, preserving a valid predecessor on failure.'''

    safe_original = safe_upload_name(original_name)
    extension = Path(safe_original).suffix.lower()
    valid_docx, message = _validate_payload(payload, extension)
    digest = sha256(payload).hexdigest()
    if existing_record is not None:
        existing = UploadRecord.from_dict(existing_record)
        existing_path = Path(existing.temporary_path)
        if (existing.sha256 == digest and existing_path.is_file()
                and _sha256_path(existing_path) == digest):
            return existing.to_dict()

    draft = Path(draft_directory).expanduser().resolve()
    uploads = (draft / 'uploads').resolve()
    if uploads.parent != draft:
        raise ValueError('unsafe wizard uploads directory')
    uploads.mkdir(parents=True, exist_ok=True)
    stem = Path(safe_original).stem[:80].strip(' ._-') or 'upload'
    immutable_name = f'{role}-{stem}-{digest[:12]}{extension}'
    target = (uploads / immutable_name).resolve()
    if target.parent != uploads:
        raise ValueError('uploaded filename escaped the wizard directory')
    if not target.exists() or _sha256_path(target) != digest:
        _atomic_write(target, payload)

    record = UploadRecord(
        role=role,
        original_name=original_name,
        safe_name=immutable_name,
        extension=extension,
        mime_type=mime_type or 'application/octet-stream',
        size_bytes=len(payload),
        sha256=digest,
        temporary_path=str(target),
        valid_docx=valid_docx,
        non_empty=True,
        validation_message=message,
        uploaded_at=utc_now(),
    )
    return record.to_dict()


def validate_record(
    record_value: Mapping[str, Any] | None, *, expected_role: str,
) -> dict[str, Any]:
    result = {
        'role': expected_role,
        'record_present': False,
        'file_name': '',
        'size_bytes': 0,
        'non_empty': False,
        'valid_docx': False,
        'sha256': '',
        'temporary_file_exists': False,
        'hash_matches': False,
        'readable': False,
        'ready': False,
        'message': '',
    }
    if not record_value:
        result['message'] = (
            'Reviewer comments DOCX has not been saved.'
            if expected_role == REVIEWER_ROLE
            else 'Manuscript DOCX has not been saved.'
        )
        return result
    try:
        record = UploadRecord.from_dict(record_value)
    except (KeyError, TypeError, ValueError):
        result['message'] = 'The saved upload record is invalid; please select the file again.'
        return result
    result.update({
        'record_present': True,
        'file_name': record.original_name,
        'size_bytes': record.size_bytes,
        'non_empty': record.non_empty and record.size_bytes > 0,
        'valid_docx': record.valid_docx,
        'sha256': record.sha256,
    })
    if record.role != expected_role:
        result['message'] = f'The saved upload has the wrong role ({record.role}).'
        return result
    path = Path(record.temporary_path)
    if not path.is_file():
        result['message'] = 'The temporary upload is missing; please select the file again.'
        return result
    result['temporary_file_exists'] = True
    try:
        payload = path.read_bytes()
        result['readable'] = True
    except OSError:
        result['message'] = 'The temporary upload is unreadable; please select the file again.'
        return result
    current_hash = sha256(payload).hexdigest()
    if current_hash != record.sha256:
        result['message'] = 'The uploaded file changed after validation and must be revalidated.'
        return result
    result['hash_matches'] = True
    try:
        valid_docx, _ = validate_docx_bytes(payload)
    except WizardUploadError as exc:
        result['message'] = str(exc)
        return result
    result['valid_docx'] = valid_docx
    result['non_empty'] = bool(payload)
    result['ready'] = all((
        result['non_empty'], result['valid_docx'], result['temporary_file_exists'],
        result['hash_matches'], result['readable'],
    ))
    result['message'] = 'Ready.' if result['ready'] else 'Return to Step 3 and upload a non-empty valid DOCX file.'
    return result


def remove_upload(
    record_value: Mapping[str, Any] | None, *, draft_directory: str | Path,
) -> None:
    if not record_value:
        return
    record = UploadRecord.from_dict(record_value)
    draft = Path(draft_directory).expanduser().resolve()
    uploads = (draft / 'uploads').resolve()
    path = Path(record.temporary_path).expanduser().resolve()
    if path.parent != uploads:
        raise ValueError('refusing to remove an upload outside this wizard draft')
    path.unlink(missing_ok=True)


FORM_METADATA_KEYS = (
    'wiz_project_name', 'wiz_manuscript_id', 'wiz_title', 'wiz_journal',
    'wiz_round', 'wiz_reviewer_count', 'wiz_manuscript_language',
    'wiz_response_language', 'wiz_citation_style', 'wiz_result_status',
    'wiz_workspace', 'workspace_root',
)


def write_manifest(
    *, draft_id: str, draft_directory: str | Path,
    form_metadata: Mapping[str, Any], uploads: Mapping[str, Mapping[str, Any]],
    current_step: int, created_at: str | None = None,
    events: list[dict[str, Any]] | None = None,
) -> Path:
    directory = Path(draft_directory).expanduser().resolve()
    manifest_path = directory / MANIFEST_NAME
    prior_created = created_at
    if manifest_path.is_file() and prior_created is None:
        try:
            prior_created = json.loads(manifest_path.read_text(encoding='utf-8')).get('created_at')
        except (OSError, json.JSONDecodeError, AttributeError):
            prior_created = None
    payload = {
        'draft_id': draft_id,
        'draft_directory': str(directory),
        'form_metadata': {key: form_metadata[key] for key in FORM_METADATA_KEYS if key in form_metadata},
        'uploads': {role: dict(record) for role, record in uploads.items()},
        'current_step': max(1, min(5, int(current_step))),
        'created_at': prior_created or utc_now(),
        'modified_at': utc_now(),
        'events': list(events or []),
    }
    _atomic_write(
        manifest_path,
        (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'),
    )
    return manifest_path


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or not payload.get('draft_id'):
        raise ValueError('wizard draft manifest is invalid')
    declared = Path(str(payload.get('draft_directory', ''))).expanduser().resolve()
    if declared != manifest_path.parent or str(payload['draft_id']) != declared.name:
        raise ValueError('wizard draft manifest location is invalid')
    return payload


def find_recoverable_drafts(
    draft_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    root = Path(draft_root or default_draft_root()).expanduser().resolve()
    if not root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    for manifest_path in root.glob(f'*/{MANIFEST_NAME}'):
        try:
            manifest = load_manifest(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        uploads = manifest.get('uploads', {})
        if not isinstance(uploads, dict):
            continue
        metadata = manifest.get('form_metadata', {})
        if not uploads and not any(
            value for key, value in dict(metadata).items()
            if key not in {'workspace_root', 'wiz_workspace'}
        ):
            continue
        ready_uploads = {
            role: record for role, record in uploads.items()
            if isinstance(record, dict)
            and (
                role not in REQUIRED_ROLES
                or validate_record(record, expected_role=role)['ready']
            )
        }
        manifest['uploads'] = ready_uploads
        candidates.append(manifest)
    candidates.sort(key=lambda item: str(item.get('modified_at', '')), reverse=True)
    return candidates


def restore_manifest(
    manifest: Mapping[str, Any], state: MutableMapping[str, Any],
    *, role_record_keys: Mapping[str, str],
) -> None:
    state['new_project_draft_id'] = str(manifest['draft_id'])
    state['new_project_draft_directory'] = str(manifest['draft_directory'])
    state['wizard_step'] = max(1, min(5, int(manifest.get('current_step', 1))))
    for key, value in dict(manifest.get('form_metadata', {})).items():
        if key in FORM_METADATA_KEYS:
            state[key] = value
    for role, record in dict(manifest.get('uploads', {})).items():
        record_key = role_record_keys.get(role)
        if record_key and isinstance(record, dict):
            state[record_key] = record
    state['new_project_wizard_events'] = list(manifest.get('events', []))


def clear_draft(*, draft_id: str, draft_directory: str | Path) -> None:
    directory = Path(draft_directory).expanduser().resolve()
    base = directory.parent
    if directory.name != draft_id or base == directory or not _is_within(directory, base):
        raise ValueError('refusing to clear an unverified wizard draft directory')
    if _is_within(directory, repository_root()):
        raise ValueError('refusing to clear a wizard draft inside the repository')
    if directory.is_dir():
        shutil.rmtree(directory)
