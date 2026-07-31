from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarly_revision.models.enums import HighlightColor, ResultStatus
from scholarly_revision.models.project import ProjectManifest


def manifest_data() -> dict[str, object]:
    return {
        'project_name': 'anonymous-revision',
        'manuscript_id': 'SYNTHETIC-001',
        'manuscript_title': 'Synthetic study',
        'journal': 'Example Journal',
        'revision_round': 1,
        'manuscript_language': 'English',
        'response_language': 'English',
        'citation_style': 'journal-required',
        'reviewer_count': 2,
        'result_status': ResultStatus.DRAFT,
        'highlight_policy': {
            'reviewer_1': HighlightColor.YELLOW,
            'reviewer_2': HighlightColor.BRIGHT_GREEN,
            'shared_and_general': HighlightColor.VIOLET,
        },
        'approval_gates': {},
        'input_files': {},
        'output_names': {
            'highlighted_manuscript': 'highlighted.docx',
            'clean_manuscript': 'clean.docx',
            'revision_workbook': 'tracking.xlsx',
            'response_letter': 'response.docx',
            'qa_report': 'qa.md',
            'audit_log': 'audit.jsonl',
        },
    }


def test_valid_project_manifest() -> None:
    manifest = ProjectManifest.model_validate(manifest_data())
    assert manifest.reviewer_count == 2
    assert manifest.highlight_policy.reviewer_1 is HighlightColor.YELLOW


@pytest.mark.parametrize('field', ['reviewer_count', 'revision_round'])
def test_positive_counts_are_required(field: str) -> None:
    data = manifest_data()
    data[field] = 0
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate(data)


def test_absolute_output_path_is_rejected() -> None:
    data = manifest_data()
    output_names = dict(data['output_names'])
    output_names['qa_report'] = str(Path('C:/private/qa.md'))
    data['output_names'] = output_names
    with pytest.raises(ValidationError, match='absolute paths'):
        ProjectManifest.model_validate(data)


@pytest.mark.parametrize(
    'field_name', ['api_key', 'password', 'access_token', 'client_secret']
)
def test_secret_like_fields_are_rejected(field_name: str) -> None:
    data = manifest_data()
    data[field_name] = 'synthetic-placeholder'
    with pytest.raises(ValidationError, match='secret-like'):
        ProjectManifest.model_validate(data)


def test_manifest_schema_has_no_secret_or_content_fields() -> None:
    fields = {name.lower() for name in ProjectManifest.model_fields}
    prohibited_fragments = {'password', 'secret', 'token', 'api_key', 'content'}
    assert not any(
        fragment in field for field in fields for fragment in prohibited_fragments
    )


def test_manuscript_content_field_is_rejected() -> None:
    data = manifest_data()
    data['manuscript_content'] = 'synthetic text that must not be stored'
    with pytest.raises(ValidationError, match='manuscript content'):
        ProjectManifest.model_validate(data)
