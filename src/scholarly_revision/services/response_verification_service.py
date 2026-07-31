'''Verify response entries against manuscript, actions, logs, and registries.'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.response_package import (
    CommentResolution, LocationStatus, ResponsePackage, ResponseStatus,
)
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.response_letter_service import load_response_sources
from scholarly_revision.tools.location_verifier import verify_locations
from scholarly_revision.tools.response_docx_builder import response_docx_entry_records
from scholarly_revision.tools.docx_reader import read_docx


@dataclass(frozen=True, slots=True)
class ResponseVerificationResult:
    package: ResponsePackage
    passed: bool
    issues: tuple[dict[str, Any], ...]
    verified_count: int
    blocked_count: int
    report_path: Path


def _issue(
    issues: list[dict[str, Any]],
    code: str,
    comment_id: str,
    description: str,
) -> None:
    issues.append({
        'code': code,
        'comment_id': comment_id,
        'description': description,
        'severity': 'BLOCKER',
    })


def _manuscript_text(path: Path) -> str:
    return '\n'.join(record.text for record in read_docx(path))


def _load_package(root: Path, package: ResponsePackage | dict | str | Path | None) -> ResponsePackage:
    if package is None:
        package = read_json(root / 'working' / 'response_package.json')
    elif isinstance(package, (str, Path)):
        package = read_json(package)
    if isinstance(package, ResponsePackage):
        package = package.model_dump(mode='python')
    return ResponsePackage.model_validate(package)


def verify_response_package(
    project_root: str | Path,
    package: ResponsePackage | dict | str | Path | None = None,
    *,
    response_letter: str | Path | None = None,
) -> ResponseVerificationResult:
    root = Path(project_root).expanduser().resolve()
    response = _load_package(root, package)
    sources = load_response_sources(root)
    comments = {item.comment_id: item for item in sources['comments']}
    actions = {item.action_id: item for item in sources['actions']}
    changes = {item.change_id: item for item in sources['changes']}
    drafts = {item.draft_id: item for item in sources['drafts']}
    evidence = {str(item.get('evidence_id')): item for item in sources['evidence']}
    references = {str(item.get('reference_id')): item for item in sources['references']}
    manuscript = root / 'outputs' / 'Revised_Manuscript_Highlighted.docx'
    if not manuscript.is_file():
        raise FileNotFoundError(f'highlighted manuscript not found: {manuscript}')
    manuscript_text = _manuscript_text(manuscript)
    page_metadata_path = root / 'audit' / 'rendered_location_metadata.json'
    page_metadata = read_json(page_metadata_path) if page_metadata_path.is_file() else None
    issues: list[dict[str, Any]] = []
    updated_sections = []
    seen_comments: set[str] = set()
    seen_entries: set[str] = set()
    letter_records = None
    letter_error = None
    if response_letter is not None:
        try:
            letter_records = response_docx_entry_records(response_letter)
        except Exception as exc:
            letter_error = (
                'Response DOCX structure could not be validated: '
                f'{type(exc).__name__}: {exc}'
            )
    record_index = 0

    for section in response.sections:
        updated_entries = []
        for entry in section.entries:
            before = len(issues)
            if entry.response_entry_id in seen_entries:
                _issue(issues, 'DUPLICATE_RESPONSE', entry.comment_id, 'Duplicate response entry ID.')
            seen_entries.add(entry.response_entry_id)
            if entry.comment_id in seen_comments:
                _issue(issues, 'DUPLICATE_COMMENT', entry.comment_id, 'Reviewer comment has multiple response entries.')
            seen_comments.add(entry.comment_id)
            comment = comments.get(entry.comment_id)
            if comment is None:
                _issue(issues, 'UNKNOWN_COMMENT', entry.comment_id, 'Response has no reviewer comment record.')
            elif entry.exact_comment != comment.original_comment:
                _issue(issues, 'ALTERED_COMMENT', entry.comment_id, 'Exact reviewer comment was changed.')
            if comment is not None and entry.highlight is not comment.highlight:
                _issue(issues, 'WRONG_HIGHLIGHT', entry.comment_id, 'Response highlight conflicts with reviewer policy.')
            if entry.resolution is None:
                _issue(issues, 'MISSING_RESOLUTION', entry.comment_id, 'Comment has no explicit final response state.')
            if response_letter is not None:
                if letter_error is not None:
                    _issue(issues, 'DOCX_STRUCTURE', entry.comment_id, letter_error)
                elif letter_records is None or len(letter_records) != len(response.entries):
                    _issue(
                        issues, 'DOCX_ENTRY_COUNT', entry.comment_id,
                        'Response DOCX entry count differs from the response package.',
                    )
                if letter_records is not None and record_index < len(letter_records):
                    record = letter_records[record_index]
                    expected_heading = (
                        f'Reviewer {entry.reviewer_number}, Comment {entry.sequence_number}'
                        if entry.reviewer_source.value == 'REVIEWER' else
                        f'Editor, Comment {entry.sequence_number}'
                        if entry.reviewer_source.value == 'EDITOR' else
                        f'General Comment {entry.sequence_number}'
                    )
                    expected = {
                        'heading': expected_heading,
                        'comment': entry.exact_comment,
                        'author_response': entry.author_response or 'Response pending.',
                        'changes_made': (
                            entry.changes_made or 'No manuscript change reported.'
                        ),
                        'location': (
                            '; '.join(entry.verified_locations) or 'Not required.'
                        ),
                        'highlight': entry.highlight.value.replace('_', ' ').title(),
                    }
                    for field, value in expected.items():
                        if getattr(record, field) != value:
                            _issue(
                                issues, f'DOCX_{field.upper()}_MISMATCH',
                                entry.comment_id,
                                f'Response DOCX {field.replace("_", " ")} '
                                'differs from the validated response package.',
                            )
                    if record.heading_highlight is not entry.highlight:
                        _issue(
                            issues, 'DOCX_VISIBLE_HIGHLIGHT_MISMATCH',
                            entry.comment_id,
                            'Response DOCX heading highlight differs from policy.',
                        )
            record_index += 1
            linked_actions = [actions.get(item) for item in entry.related_action_ids]
            if any(item is None for item in linked_actions):
                _issue(issues, 'UNKNOWN_ACTION', entry.comment_id, 'Response references an unknown action.')
            for change_id in entry.related_change_ids:
                change = changes.get(change_id)
                if change is None:
                    _issue(issues, 'MISSING_CHANGE_LOG', entry.comment_id, 'Stated change has no ChangeLog record.')
                    continue
                action = actions.get(change.action_id)
                if action is None or action.approval_state.value != 'APPROVED':
                    _issue(issues, 'UNAPPROVED_CHANGE', entry.comment_id, 'ChangeLog record does not map to an approved action.')
                if change.verification_status != 'VERIFIED':
                    _issue(issues, 'UNVERIFIED_CHANGE', entry.comment_id, 'Response cites an unverified manuscript change.')
                if entry.comment_id not in change.comment_ids:
                    _issue(issues, 'CHANGE_COMMENT_MISMATCH', entry.comment_id, 'ChangeLog record maps to a different comment.')
                if action is not None and change.highlight is not action.highlight:
                    _issue(issues, 'WRONG_HIGHLIGHT', entry.comment_id, 'Response highlight conflicts with the ChangeLog record.')
                draft = drafts.get(change.draft_id)
                if draft is None:
                    _issue(issues, 'MISSING_REVISION_DRAFT', entry.comment_id, 'Applied change has no revision draft.')
                elif draft.operation.value == 'DELETE_PARAGRAPH':
                    if draft.original_text_snapshot and draft.original_text_snapshot in manuscript_text:
                        _issue(issues, 'CHANGE_ABSENT', entry.comment_id, 'Deleted text remains in the manuscript.')
                elif draft.text_for_application not in manuscript_text:
                    _issue(issues, 'CHANGE_ABSENT', entry.comment_id, 'Applied revision text is absent from the manuscript.')
            if entry.changes_made.strip() and not entry.related_change_ids:
                _issue(issues, 'FALSE_CHANGE_CLAIM', entry.comment_id, 'Response reports a change without ChangeLog IDs.')
            for evidence_id in entry.related_evidence_ids:
                item = evidence.get(evidence_id)
                if item is None or str(item.get('status')) != 'VERIFIED':
                    _issue(issues, 'MISSING_EVIDENCE', entry.comment_id, 'Response cites missing or unverified evidence.')
            for reference_id in entry.related_reference_ids:
                if reference_id not in references:
                    _issue(issues, 'MISSING_REFERENCE', entry.comment_id, 'Response cites a missing ReferenceRecord.')
            location_status = entry.location_status
            if entry.verified_locations:
                location_results = verify_locations(
                    manuscript, entry.verified_locations, page_metadata=page_metadata
                )
                if any(not item.verified for item in location_results):
                    _issue(issues, 'INVALID_LOCATION', entry.comment_id, 'One or more stated manuscript locations could not be verified.')
                    location_status = LocationStatus.UNVERIFIED
                else:
                    ranks = [
                        LocationStatus.PAGE_AND_LINES_VERIFIED,
                        LocationStatus.PAGE_VERIFIED,
                        LocationStatus.OBJECT_VERIFIED,
                        LocationStatus.SECTION_VERIFIED,
                    ]
                    location_status = next(
                        status for status in ranks
                        if any(item.status is status for item in location_results)
                    )
            elif entry.related_change_ids:
                _issue(issues, 'MISSING_LOCATION', entry.comment_id, 'A changed manuscript entry lacks a verified location.')
            if entry.resolution in {
                CommentResolution.DEFERRED,
                CommentResolution.BLOCKED_BY_MISSING_EVIDENCE,
            } and entry.changes_made.strip():
                _issue(issues, 'INCOMPLETE_AS_COMPLETE', entry.comment_id, 'Deferred or blocked work is described as completed.')
            if entry.resolution is CommentResolution.RESPECTFULLY_DECLINED and (
                not entry.author_approved or not (entry.author_justification or '').strip()
            ):
                _issue(issues, 'UNAPPROVED_DECLINE', entry.comment_id, 'Declined request lacks author-approved justification.')
            if entry.resolution is CommentResolution.PARTIALLY_ADDRESSED and not entry.unresolved_limitations:
                _issue(issues, 'HIDDEN_LIMITATION', entry.comment_id, 'Partial response does not state its unresolved limitation.')
            status = ResponseStatus.VERIFIED if len(issues) == before else ResponseStatus.BLOCKED
            try:
                updated = entry.model_copy(update={
                    'response_status': status,
                    'location_status': location_status,
                })
                updated = type(entry).model_validate(updated.model_dump(mode='python'))
            except ValueError as exc:
                _issue(issues, 'MODEL_GATE', entry.comment_id, str(exc))
                updated = entry.model_copy(update={'response_status': ResponseStatus.BLOCKED})
            updated_entries.append(updated)
        updated_sections.append(section.model_copy(update={'entries': updated_entries}))
    for comment_id in sorted(set(comments) - seen_comments):
        _issue(issues, 'MISSING_RESPONSE', comment_id, 'Reviewer comment is missing from the response package.')
    passed = not issues
    package_status = ResponseStatus.VERIFIED if passed else ResponseStatus.BLOCKED
    updated_package = response.model_copy(update={
        'sections': updated_sections,
        'package_status': package_status,
        'verification_metadata': {
            **response.verification_metadata,
            'verified_at': datetime.now(UTC).isoformat(),
            'passed': passed,
            'response_letter_checked': response_letter is not None,
        },
    })
    updated_package = ResponsePackage.model_validate(
        updated_package.model_dump(mode='python')
    )
    verified_count = sum(
        item.response_status is ResponseStatus.VERIFIED for item in updated_package.entries
    )
    blocked_count = sum(
        item.response_status is ResponseStatus.BLOCKED for item in updated_package.entries
    )
    report = {
        'schema_version': 1,
        'verified_at': datetime.now(UTC).isoformat(),
        'passed': passed,
        'entry_count': len(updated_package.entries),
        'verified_count': verified_count,
        'blocked_count': blocked_count,
        'issues': issues,
        'response_letter': str(Path(response_letter).name) if response_letter else None,
    }
    report_path = write_json(root / 'audit' / 'response_verification_report.json', report)
    write_json(
        root / 'working' / 'response_package.json',
        updated_package.model_dump(mode='json'),
    )
    return ResponseVerificationResult(
        package=updated_package,
        passed=passed,
        issues=tuple(issues),
        verified_count=verified_count,
        blocked_count=blocked_count,
        report_path=report_path,
    )


class ResponseVerificationService:
    def verify(self, project_root: str | Path, package=None, **kwargs):
        return verify_response_package(project_root, package, **kwargs)
